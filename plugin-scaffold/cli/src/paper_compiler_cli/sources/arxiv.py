"""arXiv e-print acquisition.

Prefers TeX tarball (best parse fidelity) and falls back to PDF when arXiv
returns a PDF stream instead of a tarball (about 3% of papers in dense
compiles).
"""

from __future__ import annotations

import tarfile
from pathlib import Path
from typing import Optional

from ..cache import paper_source_dir
from . import SourceResult
from ._http import TokenBucket, download_pdf

ARXIV_EPRINT = "https://arxiv.org/e-print/"


def _extract_tar(archive: Path, dest_dir: Path) -> bool:
    try:
        with tarfile.open(archive, "r:*") as tf:
            tf.extractall(dest_dir, filter="data")
        return True
    except (tarfile.ReadError, EOFError):
        return False


class ArxivSource:
    name = "arxiv"

    def __init__(self, cfg) -> None:  # noqa: ANN001
        self.bucket = TokenBucket(getattr(cfg.sources, "rate_limit_rps", 2.0))

    async def fetch(self, cfg, cand) -> Optional[SourceResult]:  # noqa: ANN001
        arxiv_id = cand.external_ids.arxiv
        if not arxiv_id:
            return None
        base = paper_source_dir(cfg, cand.paper_id)
        tex_dir = base / "tex"
        if tex_dir.exists() and any(tex_dir.iterdir()):
            return SourceResult(source="arxiv_tex", cache_path=tex_dir, kind="tex")

        # arXiv e-print returns a tarball *or* a PDF depending on whether
        # the authors uploaded TeX source. We download once and probe.
        tar = base / "arxiv-source.tar.gz"
        # `download_pdf` enforces the %PDF magic; that's wrong here because
        # the e-print is usually a tarball. Use a plain streaming GET.
        from httpx import AsyncClient, HTTPError

        await self.bucket.acquire()
        try:
            async with AsyncClient(follow_redirects=True, timeout=120.0) as client:
                async with client.stream(
                    "GET",
                    f"{ARXIV_EPRINT}{arxiv_id}",
                    headers={"User-Agent": "paper-compiler/1.0"},
                ) as resp:
                    if resp.status_code != 200:
                        return None
                    tar.parent.mkdir(parents=True, exist_ok=True)
                    with open(tar, "wb") as fh:
                        async for chunk in resp.aiter_bytes(chunk_size=1 << 16):
                            fh.write(chunk)
        except HTTPError:
            return None

        if not tar.exists() or tar.stat().st_size == 0:
            return None

        head = tar.read_bytes()[:4]
        if head == b"%PDF":
            # PDF served instead of tarball; rename and report as PDF.
            pdf_dest = base / "arxiv.pdf"
            tar.rename(pdf_dest)
            return SourceResult(source="arxiv_pdf", cache_path=pdf_dest, kind="pdf")
        tex_dir.mkdir(parents=True, exist_ok=True)
        if _extract_tar(tar, tex_dir):
            return SourceResult(source="arxiv_tex", cache_path=tex_dir, kind="tex")
        return None


def build_source(cfg) -> ArxivSource:  # noqa: ANN001
    return ArxivSource(cfg)
