from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from .config import Config
from .ir import ExternalIds
from .s2_client import S2Client

ARXIV_RE = re.compile(r"(?:arxiv[:/])?(\d{4}\.\d{4,5})(v\d+)?", re.IGNORECASE)
DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)
S2_HEX_RE = re.compile(r"^[0-9a-f]{40}$", re.IGNORECASE)


@dataclass
class Candidate:
    paper_id: str
    title: str
    year: Optional[int]
    authors: list[str]
    external_ids: ExternalIds
    confidence: float
    abstract: Optional[str] = None


def _from_record(rec: dict, confidence: float = 1.0) -> Candidate:
    ext = rec.get("externalIds") or {}
    return Candidate(
        paper_id=f"s2:{rec['paperId']}",
        title=rec.get("title") or "",
        year=rec.get("year"),
        authors=[a.get("name", "") for a in rec.get("authors") or []],
        external_ids=ExternalIds(
            arxiv=ext.get("ArXiv"),
            doi=ext.get("DOI"),
            corpus_id=str(rec["corpusId"]) if rec.get("corpusId") else None,
        ),
        confidence=confidence,
        abstract=rec.get("abstract"),
    )


def _normalize(token: str) -> str:
    s = token.strip()
    parsed = urlparse(s)
    if parsed.scheme:
        path = parsed.path
        if "arxiv.org" in (parsed.netloc or ""):
            m = ARXIV_RE.search(path)
            if m:
                return f"ARXIV:{m.group(1)}"
        if "doi.org" in (parsed.netloc or ""):
            m = DOI_RE.search(path)
            if m:
                return f"DOI:{m.group(0)}"
        if "semanticscholar.org" in (parsed.netloc or ""):
            parts = [p for p in path.split("/") if p]
            if parts:
                last = parts[-1]
                if S2_HEX_RE.match(last):
                    return last
        s = parsed.path or s
    if s.lower().startswith("arxiv:"):
        return f"ARXIV:{s.split(':', 1)[1]}"
    if s.lower().startswith("doi:"):
        return f"DOI:{s.split(':', 1)[1]}"
    if s.lower().startswith("s2:"):
        return s.split(":", 1)[1]
    if ARXIV_RE.fullmatch(s):
        return f"ARXIV:{ARXIV_RE.match(s).group(1)}"
    if DOI_RE.fullmatch(s):
        return f"DOI:{s}"
    if S2_HEX_RE.match(s):
        return s
    return s


async def resolve(cfg: Config, raw_input: str) -> list[Candidate]:
    p = Path(raw_input)
    if p.exists():
        return await _resolve_local(cfg, p)
    token = _normalize(raw_input)
    async with S2Client(cfg) as client:
        if token.startswith(("ARXIV:", "DOI:")) or S2_HEX_RE.match(token):
            rec = await client.get_paper(token)
            if rec:
                return [_from_record(rec, confidence=1.0)]
        results = await client.search(raw_input, limit=5)
        return [_from_record(r, confidence=0.6) for r in results]


async def _resolve_local(cfg: Config, path: Path) -> list[Candidate]:
    title = path.stem.replace("_", " ").replace("-", " ")
    async with S2Client(cfg) as client:
        results = await client.search(title, limit=5)
        return [_from_record(r, confidence=0.4) for r in results]
