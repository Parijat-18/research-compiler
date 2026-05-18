"""Incremental ingest: add one paper to an existing compiled corpus.

Used by `/paper-compiler:wiki-ingest`. Cheaper than a full rebuild because we
reuse the existing DB + neighborhood; we only:

1. Resolve the new paper.
2. Acquire + parse it (if needed).
3. Run atom extraction on its method sections.
4. Insert papers/sections/chunks/atoms/edges into the existing DB.
5. Recompute communities (cheap on the existing in-memory graph).
6. Re-render the wiki articles + index + answers-touched.
7. Append a `## … — ingest` entry to wiki/log.md.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from .config import Config
from .resolve import resolve


async def ingest_paper_into_research(cfg: Config, raw_input: str, research_dir: Path, force: bool = False) -> int:
    from .acquire import acquire
    from .atoms.dedup import deduplicate
    from .atoms.extract import _extract_for_paper
    from .communities import detect_and_summarize, ingest_communities
    from .graph_db import (
        ingest_atoms_and_edges,
        ingest_paper as db_ingest_paper,
        open_db,
        set_meta,
        write_embeddings_vec,
        write_atom_embeddings_vec,
    )
    from .parse import parse_paper
    from .render.wiki import write_wiki
    from .render.wiki_log import append_log
    from .text_utils import scrub_placeholders  # noqa: F401 (imported for symmetry)

    db_path = research_dir / "research.db"
    if not db_path.exists():
        print(f"error: {db_path} missing — run `paper-compiler build` first", file=sys.stderr)
        return 2

    candidates = await resolve(cfg, raw_input)
    if not candidates:
        print(f"resolve failed for {raw_input!r}", file=sys.stderr)
        return 2
    cand = candidates[0]

    conn, vec_loaded = open_db(db_path)
    existing = conn.execute("SELECT 1 FROM papers WHERE paper_id = ?", (cand.paper_id,)).fetchone()
    if existing and not force:
        print(f"paper {cand.paper_id} already in DB; pass --force to re-ingest", file=sys.stderr)
        conn.close()
        return 1

    acq = await acquire(cfg, cand)
    if acq is None:
        print(f"unable to acquire {cand.paper_id} (closed access or fetch failed)", file=sys.stderr)
        conn.close()
        return 3
    paper = await parse_paper(cfg, cand, acq)

    db_ingest_paper(conn, paper, is_target=False, depth=1, acquired=True)

    # Atom extraction on this paper only (reuse the helper used by `build`).
    new_atoms: list = []
    new_evidence: list = []
    seen: dict = {}
    _extract_for_paper(
        cfg=cfg,
        paper=paper,
        atoms=new_atoms,
        evidence=new_evidence,
        seen=seen,
        ev_seq=0,
        llm_budget=cfg.compile.atom_llm_max_calls,
        edges=[],  # no classified edges yet for the new paper; the LLM still works
        is_target=False,
        priority_factor=0.6,
    )
    new_atoms = deduplicate(new_atoms)
    ingest_atoms_and_edges(conn, new_atoms, new_evidence, [])

    # Embeddings (best-effort) for the new chunks + atoms.
    if vec_loaded:
        try:
            from sentence_transformers import SentenceTransformer
            import numpy as np

            model = SentenceTransformer("BAAI/bge-small-en-v1.5")
            new_chunks = list(
                conn.execute(
                    "SELECT chunk_id, text FROM chunks WHERE paper_id = ? AND is_indexed = 1",
                    (cand.paper_id,),
                )
            )
            if new_chunks:
                vecs = model.encode([r[1] for r in new_chunks], normalize_embeddings=True, show_progress_bar=False)
                write_embeddings_vec(conn, [r[0] for r in new_chunks], np.asarray(vecs, dtype="float32"))
            if new_atoms:
                # Re-embed *all* atoms (new + existing) since atoms_vec is rebuilt wholesale.
                all_atoms_rows = list(conn.execute("SELECT atom_id, name, description FROM atoms"))
                texts = [f"{r[1]}. {r[2] or ''}" for r in all_atoms_rows]
                vecs = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
                write_atom_embeddings_vec(conn, [r[0] for r in all_atoms_rows], np.asarray(vecs, dtype="float32"))
        except Exception as e:  # noqa: BLE001
            print(f"embedding refresh failed: {e}", file=sys.stderr)

    # Recluster communities from the full DB graph.
    all_atoms = _load_atoms_from_db(conn)
    paper_records = _load_paper_records_from_db(conn)
    communities = detect_and_summarize(cfg, all_atoms, [], paper_records)
    if communities:
        ingest_communities(conn, communities)

    set_meta(conn, "compiled_at", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    conn.commit()

    # Re-render the wiki (cheap — markdown files only).
    try:
        write_wiki(research_dir / "wiki", _wiki_papers_dict(paper_records), all_atoms, _load_evidence_from_db(conn), [], communities)
    except Exception as e:  # noqa: BLE001
        print(f"wiki re-render skipped: {e}", file=sys.stderr)

    append_log(
        research_dir / "wiki",
        "ingest",
        [
            f"paper: `{cand.paper_id}`",
            f"title: {cand.title[:80]}",
            f"new atoms: {len(new_atoms)}",
            f"total atoms now: {len(all_atoms)}",
            f"communities: {len(communities)}",
        ],
    )

    conn.close()
    print(f"ingested {cand.paper_id} (+{len(new_atoms)} atoms)", file=sys.stderr)
    return 0


def _load_atoms_from_db(conn) -> list:
    from .atoms import Atom

    out: list[Atom] = []
    for r in conn.execute("SELECT atom_id, name, category, defined_by_paper_id, description, priority FROM atoms"):
        used_by = [u["paper_id"] for u in conn.execute("SELECT paper_id FROM atom_paper_usage WHERE atom_id = ?", (r["atom_id"],))]
        ev_ids = [u["evidence_id"] for u in conn.execute("SELECT evidence_id FROM atom_evidence WHERE atom_id = ?", (r["atom_id"],))]
        out.append(
            Atom(
                id=r["atom_id"],
                name=r["name"],
                category=r["category"],
                defined_by_paper_id=r["defined_by_paper_id"],
                used_by_paper_ids=used_by or [r["defined_by_paper_id"]],
                description=r["description"] or "",
                evidence_span_ids=ev_ids,
                priority=r["priority"] or 1.0,
            )
        )
    return out


def _load_evidence_from_db(conn) -> list:
    from .atoms import EvidenceSpan

    out: list[EvidenceSpan] = []
    for r in conn.execute("SELECT evidence_id, atom_id, verbatim_text FROM atom_evidence"):
        out.append(
            EvidenceSpan(
                id=r["evidence_id"],
                paper_id="",
                section_id=None,
                section_type="other",
                verbatim_text=r["verbatim_text"] or "",
                supports_atom_ids=[r["atom_id"]],
            )
        )
    return out


def _load_paper_records_from_db(conn) -> dict:
    out: dict = {}
    for r in conn.execute("SELECT paper_id, title, year, venue, abstract FROM papers"):
        out[r["paper_id"]] = {
            "title": r["title"],
            "year": r["year"],
            "venue": r["venue"],
            "abstract": r["abstract"],
        }
    return out


def _wiki_papers_dict(paper_records: dict) -> dict:
    """Wrap DB records in the {metadata, …} shape `write_wiki` expects."""
    return {pid: {"metadata": rec} for pid, rec in paper_records.items()}
