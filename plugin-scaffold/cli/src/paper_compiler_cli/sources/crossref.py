"""Crossref source.

Crossref's REST API (https://api.crossref.org) is the canonical DOI
metadata service. It rarely hosts PDFs directly but exposes ``link``
records that point at publisher-hosted PDFs for content-mining. We
prefer entries with ``intended-application = 'text-mining'`` and
``content-type = 'application/pdf'``; everything else is a paywall splash.

Crossref asks for an email in the User-Agent for the "polite pool"
(faster lookups). We pass ``cfg.sources.contact_email`` automatically via
the shared user-agent builder in ``_http.py``.
"""

from __future__ import annotations

from typing import Optional

from ..cache import paper_source_dir
from . import SourceResult
from ._http import TokenBucket, download_pdf, get_json

CR_API = "https://api.crossref.org/works"


class CrossrefSource:
    name = "crossref"

    def __init__(self, cfg) -> None:  # noqa: ANN001
        self.bucket = TokenBucket(getattr(cfg.sources, "rate_limit_rps", 2.0))

    async def fetch(self, cfg, cand) -> Optional[SourceResult]:  # noqa: ANN001
        doi = cand.external_ids.doi
        if not doi:
            return None
        base = paper_source_dir(cfg, cand.paper_id)
        pdf_dest = base / "crossref.pdf"
        if pdf_dest.exists() and pdf_dest.stat().st_size > 0:
            return SourceResult(source="crossref_pdf", cache_path=pdf_dest, kind="pdf")

        record = await get_json(
            cfg,
            f"{CR_API}/{doi}",
            bucket=self.bucket,
        )
        if not record:
            return None
        msg = record.get("message") or {}
        links = msg.get("link") or []
        # Prefer explicit text-mining links (intended for programmatic access).
        sorted_links = sorted(
            links,
            key=lambda link: (
                link.get("intended-application") != "text-mining",
                link.get("content-type") != "application/pdf",
            ),
        )
        for link in sorted_links:
            url = link.get("URL")
            if not isinstance(url, str):
                continue
            if await download_pdf(cfg, url, pdf_dest, bucket=self.bucket):
                return SourceResult(source="crossref_pdf", cache_path=pdf_dest, kind="pdf")
        return None


def build_source(cfg) -> CrossrefSource:  # noqa: ANN001
    return CrossrefSource(cfg)
