"""Pluggable paper-acquisition sources.

The v0.2 pipeline hard-coded ``arxiv → S2 openAccessPdf → local PDF``. That
covered arXiv well, missed everything else, and recorded no provenance. v1.0
turns acquisition into a registry: each source declares a ``name`` and an
async ``fetch(cfg, candidate)`` returning ``SourceResult | None``. The
orchestrator in ``acquire.py`` tries sources in ``cfg.sources.enabled``
order; the first hit wins. The winning source's name is recorded on the
``Paper.acquisition`` IR and persisted into ``papers.acquired_via`` so we
can answer "where did this paper come from?" downstream.

Default v1.0 source order:

    1. arxiv       — TeX tarball if arxiv id is present (best parse fidelity)
    2. s2          — Semantic Scholar openAccessPdf URL
    3. openalex    — OpenAlex best_oa_location PDF (250M works, no API key)
    4. unpaywall   — Unpaywall best_oa_location PDF (free with email)
    5. crossref    — Crossref TDM links + content-negotiated PDF

paperscraper (bioRxiv/medRxiv/chemRxiv/PubMed) and openreview (ICLR/NeurIPS
peer reviews + PDFs) plug into the same registry but are not enabled by
default — they require heavier deps. Add them to ``sources.enabled`` once
they're implemented.
"""

from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol, runtime_checkable

# Forward-references kept loose so individual source modules import cheap.


@dataclass
class SourceResult:
    """Outcome of a successful fetch from one source.

    ``source`` is a short stable identifier ("arxiv_tex", "openalex_pdf",
    ...) recorded into ``papers.acquired_via``. Use the source module's
    ``name`` for registry routing; use this ``source`` field for the
    specific artifact kind (a single source may produce tex OR pdf).
    """

    source: str
    cache_path: Path
    kind: str  # "tex" | "pdf"


@runtime_checkable
class PaperSource(Protocol):
    name: str

    async def fetch(self, cfg, cand) -> Optional[SourceResult]:  # noqa: ANN001
        ...


# The registry maps ``cfg.sources.enabled`` strings to module paths inside
# this subpackage. Adding a new source = drop a module here + extend this
# map. We don't auto-import on package load so failures are localized.
_SOURCE_MODULES: dict[str, str] = {
    "arxiv": "paper_compiler_cli.sources.arxiv",
    "s2": "paper_compiler_cli.sources.s2",
    "openalex": "paper_compiler_cli.sources.openalex",
    "unpaywall": "paper_compiler_cli.sources.unpaywall",
    "crossref": "paper_compiler_cli.sources.crossref",
    # Below are pluggable but opt-in; not implemented in v1.0.
    # "paperscraper": "paper_compiler_cli.sources.paperscraper_src",
    # "openreview": "paper_compiler_cli.sources.openreview",
}


def get_enabled_sources(cfg) -> list[PaperSource]:  # noqa: ANN001
    """Return live source instances in user-declared priority order.

    Missing/broken source modules are logged once and dropped from the list
    so a typo in config can't kill the whole pipeline.
    """
    out: list[PaperSource] = []
    for name in (cfg.sources.enabled or []):
        path = _SOURCE_MODULES.get(name)
        if path is None:
            print(f"sources: unknown source {name!r} (known: {sorted(_SOURCE_MODULES)})", file=sys.stderr)
            continue
        try:
            module = importlib.import_module(path)
        except Exception as e:  # noqa: BLE001
            print(f"sources: skipping {name!r}: {e}", file=sys.stderr)
            continue
        factory = getattr(module, "build_source", None)
        if factory is None:
            print(f"sources: {name!r} is missing build_source(cfg)", file=sys.stderr)
            continue
        try:
            out.append(factory(cfg))
        except Exception as e:  # noqa: BLE001
            print(f"sources: factory failed for {name!r}: {e}", file=sys.stderr)
    return out
