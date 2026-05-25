from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from .config import Config
from .resolve import resolve


async def parse_only(cfg: Config, raw_input: str, out: Path) -> int:
    from .acquire import acquire
    from .parse import parse_paper

    candidates = await resolve(cfg, raw_input)
    if not candidates:
        print(f"resolve failed for {raw_input!r}", file=sys.stderr)
        return 2
    cand = candidates[0]
    acq = await acquire(cfg, cand)
    paper = await parse_paper(cfg, cand, acq)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(paper.model_dump_json(indent=2, exclude_none=True))
    print(f"wrote {out}", file=sys.stderr)
    return 0


async def build_paper(cfg: Config, paper_id_or_input: str, out: Path, refresh: bool = False) -> int:
    from .acquire import acquire
    from .parse import parse_paper
    from .expand import expand_neighborhood
    from .classify.edge import classify_edges
    from .atoms.extract import extract_atoms
    from .score import score_papers, topological_order
    from .render.build_manifest import write_manifest
    from .render.evidence_files import write_evidence_files
    from .render.graph_json import build_graph_doc
    from .render.missing_details import write_missing_details
    from .render.research_md import render_research_md

    out.mkdir(parents=True, exist_ok=True)
    (out / "evidence").mkdir(exist_ok=True)
    # v2.0 memory layer: cross-session decisions log + per-session notes dir.
    # Created here (not by the MCP server) so the artifact ships ready for
    # writes from the Stop hook + record_decision MCP tool.
    (out / "sessions").mkdir(exist_ok=True)
    decisions_path = out / "decisions.md"
    if not decisions_path.exists():
        decisions_path.write_text(
            "# Decisions & Gotchas\n\n"
            "Append-only. Written by `mcp__paper-compiler__record_decision`.\n"
            "Each entry: H2 with ISO timestamp + slug, then **Key:** value bullets.\n",
            encoding="utf-8",
        )
    started = time.time()

    candidates = await resolve(cfg, paper_id_or_input)
    if not candidates:
        print(f"resolve failed for {paper_id_or_input!r}", file=sys.stderr)
        return 2
    target_cand = candidates[0]

    acq = await acquire(cfg, target_cand)
    target_paper = await parse_paper(cfg, target_cand, acq)

    neighborhood = await expand_neighborhood(cfg, target_paper)
    edges = await classify_edges(cfg, target_paper, neighborhood)
    atoms, evidence = await extract_atoms(cfg, target_paper, neighborhood, edges)

    from .atoms.dedup import deduplicate
    from .llm import llm_backend
    from .render.embeddings import write_embeddings

    atoms = deduplicate(atoms)
    write_embeddings(out, atoms, evidence)
    neighborhood.stats["llm_backend"] = llm_backend(cfg) or "none"

    scores = score_papers(target_paper, neighborhood, edges, atoms)
    order = topological_order(atoms)

    graph_doc = build_graph_doc(
        target=target_paper,
        neighborhood=neighborhood,
        atoms=atoms,
        evidence=evidence,
        edges=edges,
        scores=scores,
        order=order,
        elapsed=time.time() - started,
    )
    (out / "graph.json").write_text(json.dumps(graph_doc, indent=2))

    research_md = render_research_md(
        cfg=cfg,
        target=target_paper,
        graph=graph_doc,
        atoms=atoms,
        order=order,
    )
    (out / "research.md").write_text(research_md)

    write_missing_details(out / "missing-details.md", graph_doc)
    write_evidence_files(out / "evidence", atoms, evidence)

    # Detect communities + build the Graph RAG DB and wiki.
    try:
        from .communities import detect_and_summarize, ingest_communities
        from .graph_db import (
            init_schema,
            ingest_atoms_and_edges,
            ingest_missing,
            ingest_paper,
            ingest_scores,
            open_db,
            set_meta,
            write_embeddings_vec,
            write_atom_embeddings_vec,
        )
        from .render.wiki import write_wiki

        paper_records = {pid: (np.record or {}) for pid, np in neighborhood.papers.items()}
        paper_records[target_paper.paper_id] = {
            "title": target_paper.metadata.title,
            "year": target_paper.metadata.year,
            "abstract": target_paper.metadata.abstract,
        }
        communities = detect_and_summarize(cfg, atoms, edges, paper_records)

        # Phase 3: aggregate per-source acquisition counts so the manifest
        # makes "where did the corpus come from?" visible.
        sources_used: dict[str, int] = {}
        target_src = (
            target_paper.acquisition.source
            if target_paper.acquisition
            else "unavailable"
        )
        sources_used[target_src] = sources_used.get(target_src, 0) + 1
        for np in neighborhood.papers.values():
            if np.parsed is not None and np.parsed.acquisition is not None:
                src = np.parsed.acquisition.source
            else:
                src = "unavailable"
            sources_used[src] = sources_used.get(src, 0) + 1
        neighborhood.stats["papers_by_source"] = sources_used
    except Exception as e:  # noqa: BLE001
        print(f"community detection skipped: {e}", file=sys.stderr)
        communities = []

    # Sqlite Graph RAG DB.
    try:
        db_path = out / "research.db"
        if db_path.exists():
            db_path.unlink()
        conn, vec_loaded = open_db(db_path)
        init_schema(conn, vec_loaded, vec_dim=384)
        chunk_ids = ingest_paper(conn, target_paper, is_target=True, depth=0, acquired=True)
        for pid, np in neighborhood.papers.items():
            if np.parsed is not None:
                ingest_paper(conn, np.parsed, is_target=False, depth=np.depth, acquired=np.acquired)
            else:
                # metadata-only paper (no full text)
                from .ir import Acquisition, Author, Metadata, Paper as PaperIR
                rec = np.record or {}
                stub = PaperIR(
                    paper_id=pid,
                    metadata=Metadata(
                        title=rec.get("title") or pid,
                        authors=[Author(name=a.get("name", "")) for a in rec.get("authors") or []],
                        year=rec.get("year"),
                        venue=rec.get("venue"),
                        abstract=rec.get("abstract"),
                    ),
                    acquisition=Acquisition(
                        source="unavailable",
                        fetched_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    ),
                )
                ingest_paper(conn, stub, is_target=False, depth=np.depth, acquired=False)
        ingest_stats = ingest_atoms_and_edges(conn, atoms, evidence, edges) or {}
        neighborhood.stats["evidence_chunk_resolved"] = ingest_stats.get("evidence_chunk_resolved", 0)
        neighborhood.stats["evidence_total"] = ingest_stats.get("evidence_total", 0)
        from .atoms.extract import collect_missing_details
        ingest_missing(conn, collect_missing_details(target_paper, atoms))
        ingest_scores(conn, scores)
        if communities:
            ingest_communities(conn, communities)
        from .graph_db import SCHEMA_VERSION
        set_meta(conn, "schema_version", SCHEMA_VERSION)
        set_meta(conn, "target_paper_id", target_paper.paper_id)
        set_meta(conn, "compiled_at", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

        # Embeddings for chunks + atoms (best-effort).
        if vec_loaded:
            try:
                from sentence_transformers import SentenceTransformer
                import numpy as np

                # IMPORTANT: model must match chunks_vec dim (384). bge-small is
                # 384-dim; SPECTER2/SPECTER (768) would mismatch the schema.
                model = SentenceTransformer("BAAI/bge-small-en-v1.5")
                # Chunks — only embed the indexed (high-quality prose) chunks.
                rows = list(conn.execute("SELECT chunk_id, text FROM chunks WHERE is_indexed = 1"))
                if rows:
                    vecs = model.encode([r[1] for r in rows], normalize_embeddings=True, show_progress_bar=False)
                    write_embeddings_vec(conn, [r[0] for r in rows], np.asarray(vecs, dtype="float32"))
                # Atoms
                if atoms:
                    atom_texts = [f"{a.name}. {a.description}" for a in atoms]
                    vecs = model.encode(atom_texts, normalize_embeddings=True, show_progress_bar=False)
                    write_atom_embeddings_vec(conn, [a.id for a in atoms], np.asarray(vecs, dtype="float32"))
                # Communities (Phase 7): embed label + summary for the
                # "global" query mode. Empty-summary communities still get
                # an embedding from the label so KNN never misses them.
                if communities:
                    from .graph_db import write_community_embeddings_vec
                    comm_texts = [
                        f"{c.label}. {c.summary or ''}".strip() or c.label or f"Community {c.id}"
                        for c in communities
                    ]
                    vecs = model.encode(comm_texts, normalize_embeddings=True, show_progress_bar=False)
                    write_community_embeddings_vec(
                        conn,
                        [c.id for c in communities],
                        np.asarray(vecs, dtype="float32"),
                    )
            except ImportError:
                print("embeddings: sentence-transformers missing; vec tables stay empty", file=sys.stderr)
            except Exception as e:  # noqa: BLE001
                print(f"embedding failed: {e}", file=sys.stderr)

        # Phase 8: re-embed promoted wiki answers so retrieval finds them.
        # Runs AFTER chunk + atom + community embeddings so the answer
        # vectors land in the same chunks_vec table as everything else.
        try:
            from .wiki_ingest import reembed_wiki_answers
            wiki_stats = reembed_wiki_answers(conn, out, vec_loaded=vec_loaded)
            neighborhood.stats["wiki_answers_indexed"] = wiki_stats.get("answers", 0)
        except Exception as e:  # noqa: BLE001
            print(f"wiki re-embed skipped: {e}", file=sys.stderr)

        conn.commit()
        conn.close()
        print(f"db: research.db built ({db_path.stat().st_size // 1024} KB)", file=sys.stderr)
    except Exception as e:  # noqa: BLE001
        print(f"graph db build skipped: {e}", file=sys.stderr)

    # llm-wiki style article tree.
    try:
        from .render.wiki import write_wiki
        edge_dicts = []
        for ce in edges:
            role = ce.roles[0].label if ce.roles else "related_work_only"
            conf = ce.roles[0].confidence if ce.roles else 0.0
            edge_dicts.append({
                "from_paper_id": ce.edge.from_paper_id,
                "to_paper_id": ce.edge.to_paper_id,
                "best_role": role,
                "best_confidence": conf,
            })
        paper_records_full = {pid: graph_doc["papers"].get(pid, {}) for pid in graph_doc["papers"]}
        n = write_wiki(out / "wiki", paper_records_full, atoms, evidence, edge_dicts, communities)
        print(f"wiki: {n} articles", file=sys.stderr)
    except Exception as e:  # noqa: BLE001
        print(f"wiki build skipped: {e}", file=sys.stderr)

    # Write a stable schema doc for Claude to learn the DB shape.
    try:
        from .render.schema_doc import write_schema_doc
        write_schema_doc(out / "SCHEMA.md")
    except Exception as e:  # noqa: BLE001
        print(f"schema doc skipped: {e}", file=sys.stderr)

    # Wiki SCHEMA + append-only log (Karpathy llm-wiki workflow).
    try:
        from .render.wiki_schema_doc import write_wiki_schema_doc
        write_wiki_schema_doc(out / "wiki" / "SCHEMA.md")
    except Exception as e:  # noqa: BLE001
        print(f"wiki schema doc skipped: {e}", file=sys.stderr)
    try:
        from .render.wiki_log import log_compile
        log_compile(out / "wiki", target_paper.paper_id, {
            "papers_in_neighborhood": len(neighborhood.papers),
            "papers_acquired": sum(1 for np in neighborhood.papers.values() if np.acquired),
            "atoms_extracted": len(atoms),
            "communities": len(communities),
            "wall_time_seconds": round(time.time() - started, 1),
            "llm_backend": neighborhood.stats.get("llm_backend", "none"),
        })
    except Exception as e:  # noqa: BLE001
        print(f"wiki log skipped: {e}", file=sys.stderr)

    write_manifest(out / "build-manifest.json", graph_doc, target_paper, started)

    # Phase F: per-paper context fragment read by SessionStart hook so a fresh
    # Claude session sees paper-specific routing hints without making any tool
    # calls. Cheap; pure markdown render from objects already in scope.
    try:
        from .render.paper_context import write_paper_context
        from .atoms.extract import collect_missing_details
        write_paper_context(
            out / "CLAUDE-PAPER-CONTEXT.md",
            target=target_paper,
            atoms=atoms,
            graph_doc=graph_doc,
            missing_details=collect_missing_details(target_paper, atoms),
            neighborhood_stats=neighborhood.stats,
        )
    except Exception as e:  # noqa: BLE001
        print(f"paper-context render skipped: {e}", file=sys.stderr)

    print(f"compiled {target_paper.paper_id} → {out}", file=sys.stderr)
    return 0
