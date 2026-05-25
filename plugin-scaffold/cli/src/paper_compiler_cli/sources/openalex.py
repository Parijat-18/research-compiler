"""OpenAlex source.

OpenAlex (https://openalex.org) is a free, fully-open metadata service
covering 250M+ scholarly works with first-class open-access PDF locator
fields. No API key is required, but the "polite pool" (faster rate limits)
needs an email. We pass ``cfg.sources.contact_email`` when present.

We look the paper up by DOI first (most precise), then by arXiv id. If
either resolves and ``best_oa_location.pdf_url`` is present, we stream that
PDF. OpenAlex returns the openly-licensed copy when available (often a PMC
or institutional repository URL).
"""

from __future__ import annotations

from typing import Optional

from ..cache import paper_source_dir
from . import SourceResult
from ._http import TokenBucket, download_pdf, get_json

OA_API = "https://api.openalex.org/works"


def _work_url(*, doi: Optional[str], arxiv_id: Optional[str]) -> Optional[str]:
    """Build the canonical OpenAlex 'work' lookup URL."""
    if doi:
        return f"{OA_API}/https://doi.org/{doi}"
    if arxiv_id:
        # OpenAlex stores arXiv as a DOI ``10.48550/arXiv.<id>`` for ~all
        # arXiv works, but a direct arxiv lookup also resolves via search.
        return f"{OA_API}/https://doi.org/10.48550/arXiv.{arxiv_id}"
    return None


class OpenAlexSource:
    name = "openalex"

    def __init__(self, cfg) -> None:  # noqa: ANN001
        self.bucket = TokenBucket(getattr(cfg.sources, "rate_limit_rps", 2.0))

    async def fetch(self, cfg, cand) -> Optional[SourceResult]:  # noqa: ANN001
        base = paper_source_dir(cfg, cand.paper_id)
        pdf_dest = base / "openalex.pdf"
        if pdf_dest.exists() and pdf_dest.stat().st_size > 0:
            return SourceResult(source="openalex_pdf", cache_path=pdf_dest, kind="pdf")

        doi = cand.external_ids.doi
        arxiv_id = cand.external_ids.arxiv
        url = _work_url(doi=doi, arxiv_id=arxiv_id)
        if url is None:
            return None
        params = {}
        email = getattr(cfg.sources, "contact_email", None)
        if email:
            params["mailto"] = email

        record = await get_json(cfg, url, params=params, bucket=self.bucket)
        if not record:
            return None
        best = record.get("best_oa_location") or {}
        pdf_url = best.get("pdf_url") or best.get("url_for_pdf")
        if not pdf_url:
            # Sometimes the canonical pdf_url is empty but ``url`` points
            # directly at the PDF.
            cand_url = best.get("url")
            if isinstance(cand_url, str) and cand_url.lower().endswith(".pdf"):
                pdf_url = cand_url
        if not pdf_url:
            return None
        if await download_pdf(cfg, pdf_url, pdf_dest, bucket=self.bucket):
            return SourceResult(source="openalex_pdf", cache_path=pdf_dest, kind="pdf")
        return None


def build_source(cfg) -> OpenAlexSource:  # noqa: ANN001
    return OpenAlexSource(cfg)
