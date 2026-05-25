"""Acquisition orchestrator over the pluggable source registry.

v0.2 hard-coded ``arxiv → S2 openAccessPdf → local PDF``. v1.0 delegates to
the registry in ``sources/``: each enabled source declares its own fetch
strategy; the orchestrator tries them in ``cfg.sources.enabled`` order and
returns the first successful ``SourceResult``. The winning source's name is
recorded on the IR (``Paper.acquisition.source``) and persisted into
``papers.acquired_via`` so we can answer "where did this paper come from?"
downstream.

Local-PDF override: callers can pass ``local_pdf=Path(...)`` to short-circuit
the registry. Used by ``cmd_parse`` for offline debugging.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .cache import paper_source_dir
from .config import Config
from .resolve import Candidate


@dataclass
class Acquired:
    source: str       # e.g. "arxiv_tex", "openalex_pdf", "unpaywall_pdf"
    cache_path: Path
    kind: str         # "tex" | "pdf"
    fetched_at: str


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


async def acquire(
    cfg: Config,
    cand: Candidate,
    local_pdf: Optional[Path] = None,
) -> Optional[Acquired]:
    """Try each enabled source in order; return the first hit, or None."""
    if local_pdf and local_pdf.exists():
        base = paper_source_dir(cfg, cand.paper_id)
        dest = base / "local.pdf"
        dest.write_bytes(local_pdf.read_bytes())
        return Acquired(source="local_pdf", cache_path=dest, kind="pdf", fetched_at=_now())

    # Lazy import to keep the cold-import cost low when running parse-only
    # paths that already have a cached IR.
    from .sources import get_enabled_sources

    sources = get_enabled_sources(cfg)
    if not sources:
        print("acquire: no sources enabled in cfg.sources.enabled", file=sys.stderr)
        return None

    for src in sources:
        try:
            result = await src.fetch(cfg, cand)
        except Exception as e:  # noqa: BLE001
            print(f"acquire: {src.name} raised {type(e).__name__}: {e}", file=sys.stderr)
            continue
        if result is not None:
            return Acquired(
                source=result.source,
                cache_path=result.cache_path,
                kind=result.kind,
                fetched_at=_now(),
            )
    return None
