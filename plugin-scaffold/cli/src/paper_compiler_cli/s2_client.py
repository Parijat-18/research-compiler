from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Iterable, Optional
from urllib.parse import quote

import httpx
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from .cache import s2_cache_get, s2_cache_put
from .config import Config

BASE = "https://api.semanticscholar.org"

DEFAULT_PAPER_FIELDS = (
    "paperId,corpusId,externalIds,title,abstract,year,venue,authors,"
    "openAccessPdf,influentialCitationCount,citationCount,references,"
    "publicationTypes,fieldsOfStudy"
)
DEFAULT_BATCH_FIELDS = (
    "paperId,corpusId,externalIds,title,abstract,year,venue,authors,"
    "openAccessPdf,influentialCitationCount,citationCount"
)


class S2Error(RuntimeError):
    pass


@dataclass
class S2Stats:
    requests: int = 0
    cache_hits: int = 0
    rate_limit_waits: float = 0.0


class TokenBucket:
    def __init__(self, rate_per_sec: float) -> None:
        self.rate = rate_per_sec
        self._next_at = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self, stats: Optional[S2Stats] = None) -> None:
        async with self._lock:
            now = time.monotonic()
            if self._next_at > now:
                wait = self._next_at - now
                if stats is not None:
                    stats.rate_limit_waits += wait
                await asyncio.sleep(wait)
                now = time.monotonic()
            self._next_at = max(self._next_at, now) + 1.0 / self.rate


_SHARED_BUCKET: Optional[TokenBucket] = None


class S2Client:
    def __init__(self, cfg: Config, stats: Optional[S2Stats] = None) -> None:
        global _SHARED_BUCKET
        self.cfg = cfg
        self.stats = stats or S2Stats()
        headers = {"User-Agent": "paper-compiler/0.1"}
        if cfg.s2.api_key:
            headers["x-api-key"] = cfg.s2.api_key
        self._client = httpx.AsyncClient(base_url=BASE, headers=headers, timeout=60.0)
        if _SHARED_BUCKET is None:
            _SHARED_BUCKET = TokenBucket(cfg.s2.rate_limit_rps)
        self._bucket = _SHARED_BUCKET

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "S2Client":
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        await self.aclose()

    async def _request(self, method: str, url: str, *, params: dict | None = None, json: Any | None = None) -> Any:
        key = f"{method}:{url}:{params}:{json}"
        cached = s2_cache_get(self.cfg, key, ttl_days=self.cfg.cache.ttl_metadata_days)
        if cached is not None:
            self.stats.cache_hits += 1
            return cached

        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(5),
            wait=wait_exponential_jitter(initial=1, max=20),
            retry=retry_if_exception_type((httpx.HTTPError, S2Error)),
            reraise=True,
        ):
            with attempt:
                await self._bucket.acquire(self.stats)
                self.stats.requests += 1
                resp = await self._client.request(method, url, params=params, json=json)
                if resp.status_code == 429:
                    raise S2Error("rate limited")
                if resp.status_code >= 500:
                    raise S2Error(f"server error {resp.status_code}")
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                data = resp.json()
        s2_cache_put(self.cfg, key, data)
        return data

    async def get_paper(self, paper_id: str, fields: str = DEFAULT_PAPER_FIELDS) -> Optional[dict]:
        return await self._request("GET", f"/graph/v1/paper/{quote(paper_id, safe=':')}", params={"fields": fields})

    async def search(self, query: str, limit: int = 10) -> list[dict]:
        data = await self._request("GET", "/graph/v1/paper/search", params={"query": query, "limit": limit, "fields": DEFAULT_BATCH_FIELDS})
        if not data:
            return []
        return data.get("data", [])

    async def batch(self, ids: Iterable[str], fields: str = DEFAULT_BATCH_FIELDS) -> list[Optional[dict]]:
        ids_list = list(ids)
        if not ids_list:
            return []
        out: list[Optional[dict]] = []
        for i in range(0, len(ids_list), 500):
            chunk = ids_list[i : i + 500]
            data = await self._request(
                "POST",
                "/graph/v1/paper/batch",
                params={"fields": fields},
                json={"ids": chunk},
            )
            out.extend(data or [])
        return out

    async def references(self, paper_id: str, fields: str = DEFAULT_BATCH_FIELDS) -> list[dict]:
        params = {"fields": ",".join(f"citedPaper.{f}" for f in fields.split(","))}
        data = await self._request("GET", f"/graph/v1/paper/{quote(paper_id, safe=':')}/references", params={**params, "limit": 1000})
        if not data:
            return []
        items = data.get("data") or []
        return [r.get("citedPaper") for r in items if isinstance(r, dict) and r.get("citedPaper")]

    async def recommendations(self, paper_id: str, limit: int = 20) -> list[dict]:
        url = f"/recommendations/v1/papers/forpaper/{quote(paper_id, safe=':')}"
        data = await self._request("GET", url, params={"limit": limit, "fields": DEFAULT_BATCH_FIELDS})
        if not data:
            return []
        return data.get("recommendedPapers", [])
