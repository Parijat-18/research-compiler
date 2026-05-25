"""Semantic Scholar openAccessPdf source.

S2 is still useful for non-arXiv papers because it pre-indexes
openAccessPdf URLs from a wide range of publishers (BMJ, PMC, conference
proceedings, etc.) and gives us a single resolved URL per paper.
"""

from __future__ import annotations

from typing import Optional

from ..cache import paper_source_dir
from . import SourceResult
from ._http import TokenBucket, download_pdf


class S2Source:
    name = "s2"

    def __init__(self, cfg) -> None:  # noqa: ANN001
        self.bucket = TokenBucket(getattr(cfg.sources, "rate_limit_rps", 2.0))

    async def fetch(self, cfg, cand) -> Optional[SourceResult]:  # noqa: ANN001
        # Reuse the existing S2 client so we share its cache + auth.
        from ..s2_client import S2Client

        base = paper_source_dir(cfg, cand.paper_id)
        pdf_dest = base / "s2.pdf"
        if pdf_dest.exists() and pdf_dest.stat().st_size > 0:
            return SourceResult(source="s2_pdf", cache_path=pdf_dest, kind="pdf")

        async with S2Client(cfg) as client:
            rec = await client.get_paper(
                cand.paper_id.replace("s2:", ""),
                fields="paperId,openAccessPdf",
            )
        pdf_url = (rec or {}).get("openAccessPdf", {}).get("url") if rec else None
        if not pdf_url:
            return None
        if await download_pdf(cfg, pdf_url, pdf_dest, bucket=self.bucket):
            return SourceResult(source="s2_pdf", cache_path=pdf_dest, kind="pdf")
        return None


def build_source(cfg) -> S2Source:  # noqa: ANN001
    return S2Source(cfg)
