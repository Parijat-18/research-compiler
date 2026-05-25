"""Unpaywall source.

Unpaywall (https://unpaywall.org) is a free DOI → open-access PDF locator.
The API requires an email (``cfg.sources.contact_email``) so the polite
pool can identify you and ask before rate-limiting. We only attempt
Unpaywall when the candidate has a DOI.
"""

from __future__ import annotations

import sys
from typing import Optional

from ..cache import paper_source_dir
from . import SourceResult
from ._http import TokenBucket, download_pdf, get_json

UP_API = "https://api.unpaywall.org/v2"


class UnpaywallSource:
    name = "unpaywall"

    def __init__(self, cfg) -> None:  # noqa: ANN001
        self.bucket = TokenBucket(getattr(cfg.sources, "rate_limit_rps", 2.0))
        self._warned = False

    async def fetch(self, cfg, cand) -> Optional[SourceResult]:  # noqa: ANN001
        doi = cand.external_ids.doi
        if not doi:
            return None
        email = getattr(cfg.sources, "contact_email", None)
        if not email:
            if not self._warned:
                print(
                    "unpaywall: skipping — set sources.contact_email to enable.",
                    file=sys.stderr,
                )
                self._warned = True
            return None
        base = paper_source_dir(cfg, cand.paper_id)
        pdf_dest = base / "unpaywall.pdf"
        if pdf_dest.exists() and pdf_dest.stat().st_size > 0:
            return SourceResult(source="unpaywall_pdf", cache_path=pdf_dest, kind="pdf")

        record = await get_json(
            cfg,
            f"{UP_API}/{doi}",
            params={"email": email},
            bucket=self.bucket,
        )
        if not record:
            return None
        best = record.get("best_oa_location") or {}
        pdf_url = best.get("url_for_pdf") or best.get("url")
        if not pdf_url:
            return None
        if await download_pdf(cfg, pdf_url, pdf_dest, bucket=self.bucket):
            return SourceResult(source="unpaywall_pdf", cache_path=pdf_dest, kind="pdf")
        return None


def build_source(cfg) -> UnpaywallSource:  # noqa: ANN001
    return UnpaywallSource(cfg)
