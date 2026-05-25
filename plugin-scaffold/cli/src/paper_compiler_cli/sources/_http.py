"""Shared async HTTP utilities for paper sources.

Lifted from ``s2_client.py``'s retry/backoff pattern so every source benefits
from the same hardening: tenacity exponential backoff, per-source token-bucket
rate limit, 5xx → retry, 404 → None, streaming downloads with %PDF magic
check to catch HTML landing pages masquerading as PDFs.
"""

from __future__ import annotations

import asyncio
import sys
import time
from typing import Any, Optional
from pathlib import Path

import httpx
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter


class SourceError(RuntimeError):
    pass


class TokenBucket:
    def __init__(self, rate_per_sec: float) -> None:
        self.rate = max(0.1, rate_per_sec)
        self._next_at = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            if self._next_at > now:
                await asyncio.sleep(self._next_at - now)
                now = time.monotonic()
            self._next_at = max(self._next_at, now) + 1.0 / self.rate


def user_agent(cfg) -> str:  # noqa: ANN001
    """Polite UA. OpenAlex / Crossref / Unpaywall ask that we identify."""
    email = (
        getattr(getattr(cfg, "sources", None), "contact_email", None)
        or "research-compiler@example.invalid"
    )
    return f"paper-compiler/1.0 (mailto:{email})"


async def get_json(
    cfg,  # noqa: ANN001
    url: str,
    *,
    params: Optional[dict] = None,
    headers: Optional[dict] = None,
    bucket: Optional[TokenBucket] = None,
    timeout: float = 30.0,
) -> Optional[Any]:
    """Polite JSON fetch with retries. 404 → None, 5xx → retry, 4xx → raise.

    Callers should treat ``None`` as "no record" rather than a hard error.
    """
    h = {"User-Agent": user_agent(cfg), "Accept": "application/json"}
    if headers:
        h.update(headers)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(4),
            wait=wait_exponential_jitter(initial=1, max=15),
            retry=retry_if_exception_type((httpx.HTTPError, SourceError)),
            reraise=True,
        ):
            with attempt:
                if bucket is not None:
                    await bucket.acquire()
                resp = await client.get(url, params=params, headers=h)
                if resp.status_code == 404:
                    return None
                if resp.status_code == 429:
                    raise SourceError("rate limited")
                if resp.status_code >= 500:
                    raise SourceError(f"server error {resp.status_code}")
                resp.raise_for_status()
                return resp.json()
    return None


async def download_pdf(
    cfg,  # noqa: ANN001
    url: str,
    dest: Path,
    *,
    bucket: Optional[TokenBucket] = None,
    timeout: float = 120.0,
) -> bool:
    """Stream a PDF to disk; reject HTML/landing-page masquerades.

    A common acquisition failure mode is a 200 response that returns HTML
    instead of a PDF (the publisher's paywall splash). We check the first
    4 bytes for the ``%PDF`` magic and discard the file otherwise.
    """
    headers = {"User-Agent": user_agent(cfg), "Accept": "application/pdf,*/*;q=0.8"}
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            if bucket is not None:
                await bucket.acquire()
            async with client.stream("GET", url, headers=headers) as resp:
                if resp.status_code != 200:
                    return False
                dest.parent.mkdir(parents=True, exist_ok=True)
                first = b""
                with open(dest, "wb") as fh:
                    async for chunk in resp.aiter_bytes(chunk_size=1 << 16):
                        if not chunk:
                            continue
                        first = (first + chunk)[:8] if len(first) < 8 else first
                        fh.write(chunk)
        if not first.startswith(b"%PDF"):
            # Looks like HTML or some other bait. Don't keep the artifact.
            try:
                dest.unlink()
            except OSError:
                pass
            return False
        return True
    except httpx.HTTPError as e:
        print(f"download failed: {url}: {e}", file=sys.stderr)
        try:
            dest.unlink()
        except OSError:
            pass
        return False
