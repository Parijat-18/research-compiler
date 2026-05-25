from __future__ import annotations

import sys
import time
from typing import Optional

from ..acquire import Acquired
from ..cache import parsed_ir_path
from ..config import Config
from ..ir import Acquisition, Author, ExternalIds, Metadata, Paper
from ..resolve import Candidate


def _metadata_from_candidate(c: Candidate) -> Metadata:
    return Metadata(
        title=c.title,
        authors=[Author(name=n) for n in c.authors],
        year=c.year,
        abstract=c.abstract,
    )


def _empty_paper(c: Candidate, acq: Optional[Acquired]) -> Paper:
    return Paper(
        paper_id=c.paper_id,
        external_ids=c.external_ids,
        metadata=_metadata_from_candidate(c),
        acquisition=Acquisition(
            source=acq.source if acq else "unavailable",
            fetched_at=acq.fetched_at if acq else time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            cache_path=str(acq.cache_path) if acq else None,
        ) if acq is not None else Acquisition(source="unavailable", fetched_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
    )


async def parse_paper(cfg: Config, cand: Candidate, acq: Optional[Acquired]) -> Paper:
    cache_path = parsed_ir_path(cfg, cand.paper_id)
    if cache_path.exists():
        try:
            return Paper.model_validate_json(cache_path.read_text())
        except Exception:  # noqa: BLE001
            pass

    paper = _empty_paper(cand, acq)
    if acq is None:
        cache_path.write_text(paper.model_dump_json(indent=2, exclude_none=True))
        return paper

    if acq.kind == "tex":
        from .tex import parse_tex

        try:
            paper = parse_tex(paper, acq.cache_path)
        except Exception as e:  # noqa: BLE001
            print(f"tex parse failed for {cand.paper_id}: {e}", file=sys.stderr)
    if acq.kind == "pdf" or (acq.kind == "tex" and not paper.sections):
        try:
            from .pdf import parse_pdf

            pdf_path = acq.cache_path if acq.kind == "pdf" else None
            if pdf_path is not None:
                paper = parse_pdf(paper, pdf_path, backend=cfg.parser.pdf_backend)
        except ImportError as e:
            print(f"pdf parser unavailable for {cand.paper_id}: {e}", file=sys.stderr)
        except Exception as e:  # noqa: BLE001
            print(f"pdf parse failed for {cand.paper_id}: {e}", file=sys.stderr)

    cache_path.write_text(paper.model_dump_json(indent=2, exclude_none=True))
    return paper
