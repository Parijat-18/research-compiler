from __future__ import annotations

import sys
import tarfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx

from .cache import paper_source_dir
from .config import Config
from .resolve import Candidate

ARXIV_EPRINT = "https://arxiv.org/e-print/"


@dataclass
class Acquired:
    source: str
    cache_path: Path
    kind: str  # "tex" | "pdf"
    fetched_at: str


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


async def _download(url: str, dest: Path) -> bool:
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=120.0) as client:
            async with client.stream("GET", url, headers={"User-Agent": "paper-compiler/0.1"}) as resp:
                if resp.status_code != 200:
                    return False
                dest.parent.mkdir(parents=True, exist_ok=True)
                with open(dest, "wb") as fh:
                    async for chunk in resp.aiter_bytes(chunk_size=1 << 16):
                        fh.write(chunk)
        return True
    except httpx.HTTPError as e:
        print(f"download failed: {url}: {e}", file=sys.stderr)
        return False


def _extract_tar(archive: Path, dest_dir: Path) -> bool:
    try:
        with tarfile.open(archive, "r:*") as tf:
            tf.extractall(dest_dir, filter="data")
        return True
    except (tarfile.ReadError, EOFError):
        return False


async def acquire(cfg: Config, cand: Candidate, local_pdf: Optional[Path] = None) -> Optional[Acquired]:
    base = paper_source_dir(cfg, cand.paper_id)

    arxiv_id = cand.external_ids.arxiv
    if arxiv_id:
        tar = base / "arxiv-source.tar.gz"
        tex_dir = base / "tex"
        if tex_dir.exists() and any(tex_dir.iterdir()):
            return Acquired("arxiv_tex", tex_dir, "tex", _now())
        if await _download(f"{ARXIV_EPRINT}{arxiv_id}", tar):
            tex_dir.mkdir(parents=True, exist_ok=True)
            if _extract_tar(tar, tex_dir):
                return Acquired("arxiv_tex", tex_dir, "tex", _now())
            pdf_dest = base / "arxiv.pdf"
            if tar.read_bytes()[:4] == b"%PDF":
                tar.rename(pdf_dest)
                return Acquired("arxiv_pdf", pdf_dest, "pdf", _now())

    # try S2 openAccessPdf via fresh metadata fetch (cached)
    from .s2_client import S2Client

    async with S2Client(cfg) as client:
        rec = await client.get_paper(cand.paper_id.replace("s2:", ""), fields="paperId,openAccessPdf")
    pdf_url = (rec or {}).get("openAccessPdf", {}).get("url") if rec else None
    if pdf_url:
        pdf_dest = base / "openaccess.pdf"
        if pdf_dest.exists() or await _download(pdf_url, pdf_dest):
            return Acquired("s2_pdf", pdf_dest, "pdf", _now())

    if local_pdf and local_pdf.exists():
        dest = base / "local.pdf"
        dest.write_bytes(local_pdf.read_bytes())
        return Acquired("local_pdf", dest, "pdf", _now())

    return None
