"""Sqlite-backed Graph RAG helpers used by the MCP server.

The DB is built by paper-compiler-cli at compile time. We open it read-only
from the MCP server, load sqlite-vec if available, and answer query tools
with FTS5 + (optional) vector hybrid search.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import struct
import sys
from pathlib import Path
from typing import Optional

_EMBEDDER = None
_EMBEDDER_DIM = 384


def _try_load_vec(conn: sqlite3.Connection) -> bool:
    try:
        import sqlite_vec
    except ImportError:
        return False
    try:
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        return True
    except (sqlite3.OperationalError, AttributeError):
        return False


def open_ro(db_path: Path) -> tuple[Optional[sqlite3.Connection], bool]:
    if not db_path.exists():
        return None, False
    uri = f"file:{db_path}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
    except sqlite3.OperationalError:
        conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    vec = _try_load_vec(conn)
    return conn, vec


def _embedder():
    global _EMBEDDER
    if _EMBEDDER is None:
        try:
            from sentence_transformers import SentenceTransformer

            _EMBEDDER = SentenceTransformer("BAAI/bge-small-en-v1.5")
        except Exception:  # noqa: BLE001
            _EMBEDDER = False
    return _EMBEDDER or None


def _embed(text: str):
    m = _embedder()
    if m is None:
        return None
    vec = m.encode([text], normalize_embeddings=True)[0]
    return vec


def _vec_blob(vec) -> bytes:
    return struct.pack(f"{len(vec)}f", *[float(x) for x in vec])


SNIPPET_CHARS = 240  # default per-chunk preview length when `full=False`

# ---------- Phase 7: query-time Graph RAG ---------- #

_RERANKER = None


def _reranker():
    """Lazy-load a cross-encoder reranker if requested by env.

    Set ``PAPER_COMPILER_RERANK_MODEL`` (e.g. ``BAAI/bge-reranker-v2-m3``).
    Loaded once per process. Returns None when unset, when the model fails
    to load, or when sentence-transformers isn't installed — callers must
    handle both branches.
    """
    global _RERANKER
    if _RERANKER is None:
        name = os.environ.get("PAPER_COMPILER_RERANK_MODEL", "").strip()
        if not name:
            _RERANKER = False
        else:
            try:
                from sentence_transformers import CrossEncoder
                _RERANKER = CrossEncoder(name)
            except Exception as e:  # noqa: BLE001
                print(f"reranker load failed ({name}): {e}", file=sys.stderr)
                _RERANKER = False
    return _RERANKER or None


def _rerank(query: str, items: list[dict], top_n: int) -> list[dict]:
    """Cross-encoder rerank `items` by ``(query, text)`` pairs.

    No-op (returns items[:top_n]) when no reranker is configured or when
    items lack a usable text field. Adds a ``rerank_score`` key so callers
    can see what the model produced.
    """
    if not items:
        return items
    model = _reranker()
    if model is None:
        return items[:top_n]
    pairs = [(query, it.get("text") or it.get("snippet") or "") for it in items]
    try:
        scores = model.predict(pairs)
    except Exception as e:  # noqa: BLE001
        print(f"rerank failed: {e}", file=sys.stderr)
        return items[:top_n]
    for it, s in zip(items, scores):
        it["rerank_score"] = float(s)
    items.sort(key=lambda x: x.get("rerank_score", 0.0), reverse=True)
    return items[:top_n]


# Router heuristics. v1.0: domain-neutral. Global = broad/comparative;
# Local = specific entity/value/equation/identifier lookups. Examples
# work for ML ("which optimizer"), physics ("what integrator"), chemistry
# ("what catalyst"), biology ("what protocol"). The router is a router,
# not a domain detector — it just picks retrieval shape from question shape.
_GLOBAL_PATTERNS = re.compile(
    r"\b(survey|overview|landscape|big picture|in general|across|"
    r"compare (?:methods|approaches|papers|results|protocols)|"
    r"state of the (?:art|field)|sota|main themes?|"
    r"key papers?|recent work|broadly|space of|"
    r"what is the field)\b",
    re.IGNORECASE,
)
_LOCAL_PATTERNS = re.compile(
    # generic entity/value lookups: ask about *a specific thing* the paper uses
    r"(\b(?:what|which|how)\s+(?:is\s+the\s+)?"
    r"(?:method|model|scheme|algorithm|architecture|"
    r"objective|loss|function|criterion|dataset|benchmark|measurement|"
    r"corpus|protocol|procedure|optimizer|solver|integrator|scheduler|"
    r"reaction(?:\s+conditions?)?|catalyst|reagent|conditions|"
    r"parameter|hyperparameter|setting|temperature|threshold|coefficient|"
    r"equation|formula|theorem|principle|baseline|reference)\b)"
    r"|(\bvalue of\b)|(\barxiv\b)|(\bs2:[a-f0-9]+\b)|(\bcite[ds]?\b)|"
    r"(\bimplementation of\b)|(\barchitecture\s+of\b)|"
    r"(\bwhat\s+is\s+the\s+\w+)",
    re.IGNORECASE,
)

def route_query(query: str) -> str:
    """Pick a retrieval mode from the query text alone.

    Cheap, deterministic, no LLM call. Returns one of:
      - ``"global"`` — broad/thematic/comparative questions
      - ``"local"`` — specific entity/value/architecture lookups
      - ``"hybrid"`` — neither rule fires (default)

    The caller is free to override via ``mode=...``. The rules are tuned
    for the JEPA audit: "survey latent world models" → global; "what loss
    does JEPA use" → local.
    """
    q = query.strip()
    if not q:
        return "hybrid"
    if _GLOBAL_PATTERNS.search(q):
        return "global"
    if _LOCAL_PATTERNS.search(q):
        return "local"
    return "hybrid"


def _top_communities(
    conn: sqlite3.Connection,
    vec_loaded: bool,
    query: str,
    *,
    k: int = 3,
) -> list[dict]:
    """Return the top-k communities most relevant to ``query``.

    Uses communities_vec (Phase 7's new vec0 table). Falls back to BM25-like
    title/summary substring matching when sqlite-vec isn't available.
    """
    if vec_loaded:
        v = _embed(query)
        if v is not None:
            try:
                cur = conn.execute(
                    """
                    SELECT c.community_id, c.label, c.summary, c.size, cv.distance
                    FROM communities_vec cv
                    JOIN communities c ON c.community_id = cv.rowid
                    WHERE cv.embedding MATCH ? AND k = ?
                    ORDER BY cv.distance
                    """,
                    (_vec_blob(v), int(k)),
                )
                rows = list(cur)
                if rows:
                    return [
                        {
                            "community_id": r["community_id"],
                            "label": r["label"],
                            "summary": r["summary"],
                            "size": r["size"],
                            "distance": float(r["distance"]),
                        }
                        for r in rows
                    ]
            except sqlite3.OperationalError as e:
                print(f"communities_vec query failed: {e}", file=sys.stderr)

    # Fallback: lexical match on label/summary.
    q_low = (query or "").lower()
    cur = conn.execute("SELECT community_id, label, summary, size FROM communities")
    scored = []
    for r in cur:
        text = f"{r['label'] or ''} {r['summary'] or ''}".lower()
        hits = sum(1 for tok in _tokenize_for_fts(q_low) if tok in text)
        if hits:
            scored.append((hits, dict(r)))
    scored.sort(key=lambda kv: -kv[0])
    return [dict(s[1], distance=1.0 / s[0]) for s in scored[:k]]


def query_local(
    conn: sqlite3.Connection,
    vec_loaded: bool,
    query: str,
    *,
    limit: int = 8,
    full: bool = False,
    max_per_paper: int = 2,
    community_boost: float = 0.15,
) -> dict:
    """Local mode — chunk hybrid retrieval with a community-membership boost.

    Wraps ``query_chunks``: candidates from papers belonging to the query's
    top community get ``+community_boost`` added to their _score before
    rerank/diversification. This is the GraphRAG "local" pattern.
    """
    base = query_chunks(conn, vec_loaded, query, limit=limit * 2, full=True, max_per_paper=limit * 2)
    results = base["results"]
    if not results:
        return base

    top_comms = _top_communities(conn, vec_loaded, query, k=1)
    if top_comms:
        cid = top_comms[0]["community_id"]
        comm_paper_set = {
            r["paper_id"]
            for r in conn.execute(
                "SELECT paper_id FROM community_papers WHERE community_id = ?", (cid,)
            )
        }
        for r in results:
            if r.get("paper_id") in comm_paper_set:
                r["_community_boost"] = community_boost
                r["community_id"] = cid

    # Rerank by base rank position + boost, then diversify + crop to limit.
    for i, r in enumerate(results):
        r["_score"] = (-i) + r.get("_community_boost", 0.0)
    results.sort(key=lambda x: x["_score"], reverse=True)
    diversified = _diversity_rerank(results, limit=limit, max_per_paper=max_per_paper)

    out: list[dict] = []
    for it in diversified:
        entry = {k: v for k, v in it.items() if k not in {"_score", "_community_boost"}}
        if not full:
            entry.pop("text", None)
        out.append(entry)
    return {"results": out, "mode": "local", "anchor_community": top_comms[0] if top_comms else None}


def query_global(
    conn: sqlite3.Connection,
    vec_loaded: bool,
    query: str,
    *,
    limit: int = 8,
    full: bool = False,
    community_k: int = 3,
) -> dict:
    """Global mode — community-summary-first synthesis context.

    Returns the top-k communities' summaries plus a small bundle of
    representative atoms and chunks from each community's member papers.
    Mirrors the Microsoft GraphRAG "global" pattern (community summaries
    are the primary retrieval unit; the LLM later composes an answer over
    them). Useful for broad/thematic questions where no single chunk has
    "the answer".
    """
    top = _top_communities(conn, vec_loaded, query, k=community_k)
    if not top:
        # No communities yet — degrade to local.
        return {"mode": "global_fallback_local", **query_local(conn, vec_loaded, query, limit=limit, full=full)}

    communities_out: list[dict] = []
    for comm in top:
        cid = comm["community_id"]
        paper_rows = list(conn.execute(
            """
            SELECT p.paper_id, p.title, p.rank FROM community_papers cp
            JOIN papers p ON p.paper_id = cp.paper_id
            WHERE cp.community_id = ?
            ORDER BY COALESCE(p.rank, 0) DESC LIMIT 5
            """,
            (cid,),
        ))
        atom_rows = list(conn.execute(
            """
            SELECT a.atom_id, a.atom_uid, a.name, a.category, a.subcategory, a.priority
            FROM community_atoms ca JOIN atoms a ON a.atom_id = ca.atom_id
            WHERE ca.community_id = ?
            ORDER BY COALESCE(a.priority, 0) DESC LIMIT 8
            """,
            (cid,),
        ))
        # Per-community top chunks: restrict the global query to this
        # community's papers using SQL placeholders. This keeps the
        # community → evidence link traceable, not just "everything
        # vaguely related".
        comm_paper_ids = [r["paper_id"] for r in paper_rows]
        chunks: list[dict] = []
        if comm_paper_ids:
            chunks = _query_chunks_in_papers(
                conn, vec_loaded, query, comm_paper_ids, limit=max(2, limit // community_k), full=full
            )
        communities_out.append({
            "community_id": cid,
            "label": comm.get("label"),
            "summary": comm.get("summary"),
            "size": comm.get("size"),
            "distance": comm.get("distance"),
            "papers": [dict(r) for r in paper_rows],
            "atoms": [dict(r) for r in atom_rows],
            "chunks": chunks,
        })
    return {"mode": "global", "communities": communities_out}


def _query_chunks_in_papers(
    conn: sqlite3.Connection,
    vec_loaded: bool,
    query: str,
    paper_ids: list[str],
    *,
    limit: int,
    full: bool,
) -> list[dict]:
    """FTS + vec hybrid restricted to a paper subset (for global mode)."""
    if not paper_ids:
        return []
    placeholders = ",".join("?" * len(paper_ids))
    candidates: list[dict] = []
    seen: set[int] = set()

    fts_q = " OR ".join(t for t in _tokenize_for_fts(query) if t)
    if fts_q:
        try:
            cur = conn.execute(
                f"""
                SELECT c.chunk_id, c.paper_id, c.section_id, c.text, c.quality, c.chunk_kind,
                       p.title, bm25(chunks_fts) AS score
                FROM chunks_fts JOIN chunks c ON c.chunk_id = chunks_fts.rowid
                JOIN papers p ON p.paper_id = c.paper_id
                WHERE chunks_fts MATCH ? AND c.paper_id IN ({placeholders})
                ORDER BY score LIMIT ?
                """,
                (fts_q, *paper_ids, limit * 3),
            )
            for r in cur:
                seen.add(r["chunk_id"])
                candidates.append({
                    "chunk_id": r["chunk_id"],
                    "paper_id": r["paper_id"],
                    "paper_title": r["title"],
                    "section_id": r["section_id"],
                    "chunk_kind": r["chunk_kind"],
                    "text": r["text"],
                    "snippet": (r["text"] or "")[:SNIPPET_CHARS],
                    "quality": float(r["quality"]) if r["quality"] is not None else 1.0,
                    "bm25_score": float(r["score"]),
                    "source": "fts5",
                })
        except sqlite3.OperationalError:
            pass

    if vec_loaded:
        v = _embed(query)
        if v is not None:
            try:
                cur = conn.execute(
                    f"""
                    SELECT c.chunk_id, c.paper_id, c.section_id, c.text, c.quality, c.chunk_kind,
                           p.title, distance
                    FROM chunks_vec
                    JOIN chunks c ON c.chunk_id = chunks_vec.rowid
                    LEFT JOIN papers p ON p.paper_id = c.paper_id
                    WHERE embedding MATCH ? AND k = ? AND c.paper_id IN ({placeholders})
                    ORDER BY distance
                    """,
                    (_vec_blob(v), int(limit * 3), *paper_ids),
                )
                for r in cur:
                    if r["chunk_id"] in seen:
                        continue
                    candidates.append({
                        "chunk_id": r["chunk_id"],
                        "paper_id": r["paper_id"],
                        "paper_title": r["title"],
                        "section_id": r["section_id"],
                        "chunk_kind": r["chunk_kind"],
                        "text": r["text"],
                        "snippet": (r["text"] or "")[:SNIPPET_CHARS],
                        "quality": float(r["quality"]) if r["quality"] is not None else 1.0,
                        "vector_distance": float(r["distance"]),
                        "source": "vec0",
                    })
            except sqlite3.OperationalError:
                pass

    for it in candidates:
        base = -it["bm25_score"] if "bm25_score" in it else -it.get("vector_distance", 1.0)
        it["_score"] = base + 0.2 * it["quality"]
    candidates.sort(key=lambda x: x["_score"], reverse=True)
    out = candidates[:limit]
    for it in out:
        it.pop("_score", None)
        if not full:
            it.pop("text", None)
    return out


def query_hybrid(
    conn: sqlite3.Connection,
    vec_loaded: bool,
    query: str,
    *,
    limit: int = 8,
    full: bool = False,
) -> dict:
    """Hybrid mode — Reciprocal Rank Fusion over local + global chunks.

    Useful when ``route_query`` returned ``"hybrid"`` (neither pattern
    matched) — we run both and merge. Local results are kept verbatim
    (they're the high-precision branch); global contributes chunks from
    community member papers (the high-recall, thematic branch).
    """
    local = query_local(conn, vec_loaded, query, limit=limit, full=full)
    global_res = query_global(conn, vec_loaded, query, limit=limit, full=full)

    # RRF merge: chunk_id is the dedup key; missing chunk_id (atom or
    # community entries) stays separate.
    k_rrf = 60.0  # canonical k from RRF paper
    by_id: dict[str, dict] = {}

    def _add(items, src_rank_offset=0.0):
        for i, it in enumerate(items):
            cid = it.get("chunk_id")
            key = f"c:{cid}" if cid is not None else f"{it.get('source','')}:{i}"
            score = 1.0 / (k_rrf + i + src_rank_offset)
            existing = by_id.get(key)
            if existing is None:
                by_id[key] = {**it, "_rrf": score}
            else:
                existing["_rrf"] = existing.get("_rrf", 0.0) + score

    _add(local.get("results", []))
    for comm in global_res.get("communities", []):
        # Slight rank-offset so global chunks don't beat strong local ones
        # by virtue of duplicate participation; tunable.
        _add(comm.get("chunks", []), src_rank_offset=2.0)

    merged = sorted(by_id.values(), key=lambda x: x.get("_rrf", 0.0), reverse=True)[:limit]
    for it in merged:
        it.pop("_rrf", None)
        if not full:
            it.pop("text", None)
    return {
        "mode": "hybrid",
        "results": merged,
        "anchor_community": local.get("anchor_community"),
        "global_communities": [
            {k: c[k] for k in ("community_id", "label", "size", "distance")}
            for c in global_res.get("communities", [])
        ],
    }


def query(
    conn: sqlite3.Connection,
    vec_loaded: bool,
    q: str,
    *,
    mode: str = "auto",
    limit: int = 8,
    full: bool = False,
    rerank: bool = True,
) -> dict:
    """Single entry point that routes to local / global / hybrid and
    optionally cross-encoder reranks the chunk list.

    ``mode='auto'`` (default) calls ``route_query`` to pick a mode from
    the query text. Override by passing ``mode='local'|'global'|'hybrid'``.
    """
    if mode == "auto":
        mode = route_query(q)
    if mode == "global":
        out = query_global(conn, vec_loaded, q, limit=limit, full=True)
        # Rerank each community's chunks in place.
        if rerank:
            for comm in out.get("communities", []):
                comm["chunks"] = _rerank(q, comm.get("chunks", []), top_n=len(comm.get("chunks", [])))
                if not full:
                    for c in comm.get("chunks", []):
                        c.pop("text", None)
        out["route"] = "global"
        return out
    if mode == "local":
        out = query_local(conn, vec_loaded, q, limit=limit, full=True)
    elif mode == "hybrid":
        out = query_hybrid(conn, vec_loaded, q, limit=limit, full=True)
    else:
        return {"error": f"unknown mode {mode!r}; expected auto/local/global/hybrid"}

    if rerank:
        out["results"] = _rerank(q, out.get("results", []), top_n=limit)
    if not full:
        for r in out.get("results", []):
            r.pop("text", None)
    out["route"] = mode
    return out


def _diversity_rerank(items: list[dict], limit: int, max_per_paper: int = 2) -> list[dict]:
    """Maximum Marginal Relevance-ish: drop near-duplicates by paper_id.

    We don't have query/document vectors in scope here, so we use a simple
    proxy: ``no more than max_per_paper chunks from the same paper``. Keeps
    the top-ranked one per paper first; fills in remaining slots round-robin.
    """
    seen_counts: dict[str, int] = {}
    out: list[dict] = []
    for it in items:
        pid = it.get("paper_id") or ""
        if seen_counts.get(pid, 0) >= max_per_paper:
            continue
        out.append(it)
        seen_counts[pid] = seen_counts.get(pid, 0) + 1
        if len(out) >= limit:
            break
    if len(out) < limit:
        for it in items:
            if it in out:
                continue
            out.append(it)
            if len(out) >= limit:
                break
    return out


def query_chunks(
    conn: sqlite3.Connection,
    vec_loaded: bool,
    query: str,
    limit: int = 8,
    *,
    full: bool = False,
    max_per_paper: int = 2,
    kinds: Optional[list[str]] = None,
    prefer_kind: Optional[str] = None,
    quality_weight: float = 0.2,
    prefer_kind_boost: float = 0.3,
) -> dict:
    """Hybrid BM25 + sqlite-vec chunk search with kind-aware ranking.

    Phase 6: every chunk is indexed regardless of prose-quality (the v0.2
    pipeline silently dropped 60% of chunks). ``chunk_kind`` carries the
    taxonomy (prose, table, caption, reference, equation_block, answer);
    callers can:

    - ``kinds=["table"]`` to **restrict** results to tables (hard filter).
    - ``prefer_kind="table"`` to **boost** tables without excluding prose
      (additive score bump = ``prefer_kind_boost``).
    - ``quality_weight`` to dial the soft prose-quality prior up/down.

    Default ``max_per_paper=2`` diversifies so a single mega-paper can't
    crowd out the rest. Pass ``full=True`` to return verbatim chunk text;
    the default is snippet-first (≤ 240 chars).
    """
    candidates: list[dict] = []
    seen: set[int] = set()

    kind_filter_sql = ""
    kind_filter_params: list = []
    if kinds:
        placeholders = ",".join("?" * len(kinds))
        kind_filter_sql = f" AND c.chunk_kind IN ({placeholders})"
        kind_filter_params = list(kinds)

    # 1. FTS5 lexical search
    fts_q = " OR ".join(t for t in _tokenize_for_fts(query) if t)
    if fts_q:
        cur = conn.execute(
            f"""
            SELECT c.chunk_id, c.paper_id, c.section_id, c.text, c.quality, c.chunk_kind,
                   p.title, bm25(chunks_fts) AS score
            FROM chunks_fts JOIN chunks c ON c.chunk_id = chunks_fts.rowid
            LEFT JOIN papers p ON p.paper_id = c.paper_id
            WHERE chunks_fts MATCH ?{kind_filter_sql}
            ORDER BY score LIMIT ?
            """,
            (fts_q, *kind_filter_params, limit * 3),
        )
        for r in cur:
            cid = r["chunk_id"]
            seen.add(cid)
            candidates.append(
                {
                    "chunk_id": cid,
                    "paper_id": r["paper_id"],
                    "paper_title": r["title"],
                    "section_id": r["section_id"],
                    "chunk_kind": r["chunk_kind"],
                    "text": r["text"],
                    "snippet": (r["text"] or "")[:SNIPPET_CHARS],
                    "quality": float(r["quality"]) if r["quality"] is not None else 1.0,
                    "bm25_score": float(r["score"]),
                    "source": "fts5",
                }
            )

    # 2. vec0 semantic search merges in
    if vec_loaded:
        v = _embed(query)
        if v is not None:
            try:
                cur = conn.execute(
                    f"""
                    SELECT c.chunk_id, c.paper_id, c.section_id, c.text, c.quality, c.chunk_kind,
                           p.title, distance
                    FROM chunks_vec
                    JOIN chunks c ON c.chunk_id = chunks_vec.rowid
                    LEFT JOIN papers p ON p.paper_id = c.paper_id
                    WHERE embedding MATCH ? AND k = ?{kind_filter_sql}
                    ORDER BY distance
                    """,
                    (_vec_blob(v), int(limit * 3), *kind_filter_params),
                )
                for r in cur:
                    cid = r["chunk_id"]
                    if cid in seen:
                        continue
                    candidates.append(
                        {
                            "chunk_id": cid,
                            "paper_id": r["paper_id"],
                            "paper_title": r["title"],
                            "section_id": r["section_id"],
                            "chunk_kind": r["chunk_kind"],
                            "text": r["text"],
                            "snippet": (r["text"] or "")[:SNIPPET_CHARS],
                            "quality": float(r["quality"]) if r["quality"] is not None else 1.0,
                            "vector_distance": float(r["distance"]),
                            "source": "vec0",
                        }
                    )
            except sqlite3.OperationalError as e:
                print(f"vec query failed: {e}", file=sys.stderr)

    # Combined score = BM25/distance prior + soft quality prior + optional
    # kind boost. Lower BM25 is better; we invert vec distance for parity.
    for it in candidates:
        base = -it["bm25_score"] if "bm25_score" in it else -it.get("vector_distance", 1.0)
        score = base + quality_weight * it["quality"]
        if prefer_kind and it.get("chunk_kind") == prefer_kind:
            score += prefer_kind_boost
        it["_score"] = score
    candidates.sort(key=lambda x: x["_score"], reverse=True)

    diversified = _diversity_rerank(candidates, limit=limit, max_per_paper=max_per_paper)

    results: list[dict] = []
    for it in diversified:
        entry = {k: v for k, v in it.items() if k not in {"_score", "text"}}
        if full:
            entry["text"] = it["text"]
        results.append(entry)
    return {"results": results, "truncated": len(candidates) > len(diversified)}


def _tokenize_for_fts(s: str) -> list[str]:
    import re

    return [w for w in re.findall(r"[A-Za-z0-9]+", s) if len(w) > 2]


def paper_text(
    conn: sqlite3.Connection,
    paper_id: str,
    section_type: Optional[str] = None,
    *,
    paragraph_ids: Optional[list] = None,
    chunk_ids: Optional[list] = None,
    full: bool = False,
) -> dict:
    """Return chunks of one paper grouped by section.

    Default (``full=False``) yields a section index with paragraph_ids and
    snippets so Claude can decide which paragraphs to pull. ``full=True``
    inlines the full text. ``paragraph_ids`` / ``chunk_ids`` filter to exact
    paragraphs.
    """
    paper = conn.execute("SELECT title, year, abstract FROM papers WHERE paper_id = ?", (paper_id,)).fetchone()
    if paper is None:
        return {"error": f"paper {paper_id!r} not in DB"}

    base_sql = (
        "SELECT s.title AS sec_title, s.section_type, c.chunk_id, c.paragraph_id, c.text "
        "FROM chunks c LEFT JOIN sections s ON s.section_id = c.section_id "
        "WHERE c.paper_id = ?"
    )
    params: list = [paper_id]
    if section_type:
        base_sql += " AND s.section_type = ?"
        params.append(section_type)
    if paragraph_ids:
        ph = ",".join("?" * len(paragraph_ids))
        base_sql += f" AND c.paragraph_id IN ({ph})"
        params.extend(paragraph_ids)
    if chunk_ids:
        ph = ",".join("?" * len(chunk_ids))
        base_sql += f" AND c.chunk_id IN ({ph})"
        params.extend(chunk_ids)
    base_sql += " ORDER BY s.ord, c.ord"
    cur = conn.execute(base_sql, params)

    sections: list[dict] = []
    cur_section = None
    for row in cur:
        if cur_section is None or cur_section.get("title") != row["sec_title"]:
            cur_section = {
                "title": row["sec_title"],
                "section_type": row["section_type"],
                "paragraphs": [],
            }
            sections.append(cur_section)
        entry: dict = {
            "paragraph_id": row["paragraph_id"],
            "chunk_id": row["chunk_id"],
            "snippet": (row["text"] or "")[:SNIPPET_CHARS],
        }
        if full:
            entry["text"] = row["text"]
        cur_section["paragraphs"].append(entry)
    return {
        "paper_id": paper_id,
        "title": paper["title"],
        "year": paper["year"],
        "abstract": paper["abstract"],
        "sections": sections,
    }


def equation_lookup(conn: sqlite3.Connection, query: str, limit: int = 10) -> list[dict]:
    """Substring search over the ``equations`` table's LaTeX bodies.

    Phase 8: wires the previously-stubbed MCP tool. The ``equations`` row
    set is populated at compile time by ``graph_db.ingest_paper`` from the
    parsed IR; we never had a query path against it until now. Returns at
    most ``limit`` rows, ordered by paper rank so target/high-rank papers
    surface first.
    """
    q = (query or "").strip()
    if not q:
        return []
    like = f"%{q}%"
    cur = conn.execute(
        """
        SELECT e.equation_id, e.paper_id, e.section_id, e.latex, p.title, p.rank
        FROM equations e
        LEFT JOIN papers p ON p.paper_id = e.paper_id
        WHERE e.latex LIKE ?
        ORDER BY COALESCE(p.rank, 0) DESC, e.equation_id
        LIMIT ?
        """,
        (like, int(limit)),
    )
    return [
        {
            "equation_id": r["equation_id"],
            "paper_id": r["paper_id"],
            "paper_title": r["title"],
            "section_id": r["section_id"],
            "latex": r["latex"],
        }
        for r in cur
    ]


def community_summary(conn: sqlite3.Connection, community_id: int) -> dict:
    row = conn.execute("SELECT * FROM communities WHERE community_id = ?", (community_id,)).fetchone()
    if row is None:
        return {"error": f"community {community_id} not found"}
    papers = [
        dict(r)
        for r in conn.execute(
            "SELECT p.paper_id, p.title, p.year, p.rank FROM community_papers cp "
            "JOIN papers p ON p.paper_id = cp.paper_id WHERE cp.community_id = ? ORDER BY p.rank DESC",
            (community_id,),
        )
    ]
    atoms = [
        dict(r)
        for r in conn.execute(
            "SELECT a.atom_id, a.name, a.category FROM community_atoms ca "
            "JOIN atoms a ON a.atom_id = ca.atom_id WHERE ca.community_id = ?",
            (community_id,),
        )
    ]
    return {
        "community_id": community_id,
        "label": row["label"],
        "summary": row["summary"],
        "size": row["size"],
        "papers": papers,
        "atoms": atoms,
    }


def list_communities(conn: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in conn.execute("SELECT community_id, label, size FROM communities ORDER BY size DESC")]


_ALLOWED_SQL_PREFIX = ("select", "with")


def safe_sql(conn: sqlite3.Connection, sql: str, params: Optional[list] = None, limit: int = 100) -> dict:
    """Read-only SQL escape hatch. Refuses anything but SELECT/WITH."""
    stripped = sql.strip().lower()
    if not stripped.startswith(_ALLOWED_SQL_PREFIX):
        return {"error": "only SELECT/WITH queries are allowed"}
    if ";" in sql.rstrip(";"):
        return {"error": "single statement only"}
    try:
        cur = conn.execute(sql, params or [])
    except sqlite3.Error as e:
        return {"error": str(e)}
    cols = [c[0] for c in cur.description] if cur.description else []
    rows = [dict(zip(cols, row)) for row in cur.fetchmany(limit)]
    return {"columns": cols, "rows": rows, "truncated": cur.fetchone() is not None}


def schema_doc_text(research_dir: Path) -> str:
    schema_path = research_dir / "SCHEMA.md"
    if schema_path.exists():
        return schema_path.read_text()
    return "SCHEMA.md not found — DB may be from an older compile."


# ---------- Graph traversal helpers ----------


def _is_atom(conn: sqlite3.Connection, node_id: str) -> bool:
    return conn.execute("SELECT 1 FROM atoms WHERE atom_id = ?", (node_id,)).fetchone() is not None


def _is_paper(conn: sqlite3.Connection, node_id: str) -> bool:
    return conn.execute("SELECT 1 FROM papers WHERE paper_id = ?", (node_id,)).fetchone() is not None


def neighborhood_subgraph(
    conn: sqlite3.Connection,
    node_id: str,
    *,
    hops: int = 2,
    role_filter: Optional[str] = None,
    limit: int = 40,
) -> dict:
    """BFS-expand a node by ``hops`` over `edges` (papers) and `atom_paper_usage` (atoms).

    Returns a labeled subgraph: root, nodes, edges, plus a ``via_atoms`` list of
    atoms that bridge any two papers in the subgraph (useful for "why are these
    two papers connected?" questions).
    """
    if _is_atom(conn, node_id):
        kind = "atom"
        root_label = conn.execute("SELECT name FROM atoms WHERE atom_id = ?", (node_id,)).fetchone()[0]
    elif _is_paper(conn, node_id):
        kind = "paper"
        root_label = conn.execute("SELECT title FROM papers WHERE paper_id = ?", (node_id,)).fetchone()[0]
    else:
        return {"error": f"node {node_id!r} not found in DB"}

    nodes: dict[str, dict] = {}
    edges_out: list[dict] = []

    def _add_paper_node(pid: str) -> None:
        if pid in nodes:
            return
        row = conn.execute("SELECT title FROM papers WHERE paper_id = ?", (pid,)).fetchone()
        nodes[pid] = {"id": pid, "kind": "paper", "label": row[0] if row else pid}

    def _add_atom_node(aid: str) -> None:
        if aid in nodes:
            return
        row = conn.execute("SELECT name, category FROM atoms WHERE atom_id = ?", (aid,)).fetchone()
        nodes[aid] = {
            "id": aid,
            "kind": "atom",
            "label": row[0] if row else aid,
            "category": row[1] if row else None,
        }

    if kind == "atom":
        _add_atom_node(node_id)
    else:
        _add_paper_node(node_id)

    frontier: set[str] = {node_id}
    visited: set[str] = {node_id}

    for hop in range(hops):
        next_frontier: set[str] = set()
        for current in frontier:
            if _is_paper(conn, current):
                # paper → outgoing + incoming citation edges
                q = "SELECT edge_id, from_paper_id, to_paper_id, best_role, best_confidence FROM edges WHERE (from_paper_id=? OR to_paper_id=?)"
                params: list = [current, current]
                if role_filter:
                    q += " AND best_role = ?"
                    params.append(role_filter)
                q += " LIMIT ?"
                params.append(limit)
                for r in conn.execute(q, params):
                    other = r["to_paper_id"] if r["from_paper_id"] == current else r["from_paper_id"]
                    _add_paper_node(other)
                    edges_out.append(
                        {
                            "src": r["from_paper_id"],
                            "dst": r["to_paper_id"],
                            "kind": "citation",
                            "role": r["best_role"],
                            "confidence": r["best_confidence"],
                        }
                    )
                    if other not in visited:
                        next_frontier.add(other)
                # paper → atoms it defines / uses
                for r in conn.execute(
                    "SELECT atom_id FROM atoms WHERE defined_by_paper_id = ? UNION SELECT atom_id FROM atom_paper_usage WHERE paper_id = ?",
                    (current, current),
                ):
                    aid = r["atom_id"]
                    _add_atom_node(aid)
                    edges_out.append({"src": current, "dst": aid, "kind": "has_atom"})
                    if aid not in visited:
                        next_frontier.add(aid)
            else:
                # atom → defining paper + using papers
                row = conn.execute("SELECT defined_by_paper_id FROM atoms WHERE atom_id = ?", (current,)).fetchone()
                if row and row[0]:
                    _add_paper_node(row[0])
                    edges_out.append({"src": row[0], "dst": current, "kind": "defines"})
                    if row[0] not in visited:
                        next_frontier.add(row[0])
                for r in conn.execute(
                    "SELECT paper_id FROM atom_paper_usage WHERE atom_id = ? LIMIT ?",
                    (current, limit),
                ):
                    pid = r["paper_id"]
                    _add_paper_node(pid)
                    edges_out.append({"src": pid, "dst": current, "kind": "uses_atom"})
                    if pid not in visited:
                        next_frontier.add(pid)
        visited.update(next_frontier)
        frontier = next_frontier
        if not frontier:
            break

    # via_atoms: pairs of papers connected through a common atom inside this subgraph
    paper_ids = [n["id"] for n in nodes.values() if n["kind"] == "paper"]
    via_atoms: list[dict] = []
    if len(paper_ids) >= 2:
        placeholders = ",".join("?" * len(paper_ids))
        rows = conn.execute(
            f"""
            SELECT u.atom_id, a.name AS atom_name, GROUP_CONCAT(DISTINCT u.paper_id) AS papers
            FROM atom_paper_usage u JOIN atoms a ON a.atom_id = u.atom_id
            WHERE u.paper_id IN ({placeholders})
            GROUP BY u.atom_id HAVING COUNT(DISTINCT u.paper_id) >= 2
            LIMIT 30
            """,
            paper_ids,
        )
        for r in rows:
            via_atoms.append({"atom_id": r["atom_id"], "label": r["atom_name"], "papers": r["papers"].split(",")})

    return {
        "root": {"id": node_id, "kind": kind, "label": root_label},
        "nodes": list(nodes.values()),
        "edges": edges_out[: limit * 4],
        "via_atoms": via_atoms,
        "truncated": len(edges_out) >= limit * 4,
    }


def shortest_paths(
    conn: sqlite3.Connection,
    from_id: str,
    to_id: str,
    *,
    max_hops: int = 4,
    k: int = 3,
    role_filter: Optional[str] = None,
) -> dict:
    """Return up to k shortest paths between two papers (or any pair of nodes).

    Builds an in-memory NetworkX undirected graph over `edges` (and `atom_paper_usage`
    if either endpoint is an atom). Edge weight = 1/confidence so high-confidence
    citations are preferred.
    """
    try:
        import networkx as nx
    except ImportError:
        return {"error": "networkx not installed; install paper-compiler-cli[graph]"}

    g = nx.Graph()
    q = "SELECT from_paper_id, to_paper_id, best_role, best_confidence FROM edges"
    params: list = []
    if role_filter:
        q += " WHERE best_role = ?"
        params.append(role_filter)
    for r in conn.execute(q, params):
        w = 1.0 / max(0.1, float(r["best_confidence"] or 0.5))
        g.add_edge(r["from_paper_id"], r["to_paper_id"], weight=w, role=r["best_role"])
    # bridges through atoms in case the user asks about an atom node
    for r in conn.execute("SELECT atom_id, defined_by_paper_id FROM atoms"):
        if r["defined_by_paper_id"]:
            g.add_edge(r["atom_id"], r["defined_by_paper_id"], weight=0.5, role="defines")
    for r in conn.execute("SELECT atom_id, paper_id FROM atom_paper_usage"):
        g.add_edge(r["atom_id"], r["paper_id"], weight=0.8, role="uses_atom")

    if from_id not in g.nodes or to_id not in g.nodes:
        return {"error": "endpoint not in graph", "from_present": from_id in g.nodes, "to_present": to_id in g.nodes}

    try:
        all_simple = nx.shortest_simple_paths(g, from_id, to_id, weight="weight")
        paths: list[dict] = []
        for path in all_simple:
            if len(path) - 1 > max_hops:
                break
            steps: list[dict] = []
            for u, v in zip(path[:-1], path[1:]):
                steps.append({"from": u, "to": v, "role": g[u][v].get("role")})
            paths.append({"hops": len(path) - 1, "nodes": path, "steps": steps})
            if len(paths) >= k:
                break
        return {"from": from_id, "to": to_id, "paths": paths}
    except nx.NetworkXNoPath:
        return {"from": from_id, "to": to_id, "paths": [], "error": "no path within graph"}
