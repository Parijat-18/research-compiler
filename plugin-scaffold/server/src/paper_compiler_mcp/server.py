"""paper-compiler MCP server.

Reads research/graph.json compiled by the CLI and exposes the nine query tools
described in docs/01-PRD.md §13. Graph is loaded lazily on the first tool call
so import is fast (per docs/03-claude-code-plugin-guide.md §11).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

from . import decisions as decisions_mod
from . import sessions as sessions_mod
from .db import (
    community_summary as db_community_summary,
    equation_lookup as db_equation_lookup,
    list_communities as db_list_communities,
    neighborhood_subgraph as db_neighborhood_subgraph,
    open_ro,
    paper_text as db_paper_text,
    query as db_query,
    query_chunks as db_query_chunks,
    route_query as db_route_query,
    safe_sql,
    schema_doc_text,
    shortest_paths as db_shortest_paths,
)
from .graph import ResearchGraph

# v2.0: RESEARCH_DIR is mutable so the bind_research_dir tool can rebind at
# runtime (used by /paper-compiler:compare-corpora and /paper-compiler:port).
# The variable is a module-level Path; tools reach for it via _research_dir().
RESEARCH_DIR = Path(os.environ.get("PAPER_COMPILER_RESEARCH_DIR", "./research"))
mcp = FastMCP("paper-compiler")

_graph_cache: Optional[ResearchGraph] = None
_graph_attempted = False

_db_conn = None
_db_vec_loaded = False
_db_attempted = False


def _research_dir() -> Path:
    return RESEARCH_DIR


def _invalidate_caches() -> None:
    """Drop the graph + db caches so the next tool call re-loads from disk.

    Used by bind_research_dir when the target changes.
    """
    global _graph_cache, _graph_attempted, _db_conn, _db_vec_loaded, _db_attempted
    _graph_cache = None
    _graph_attempted = False
    if _db_conn is not None:
        try:
            _db_conn.close()
        except Exception:  # noqa: BLE001
            pass
    _db_conn = None
    _db_vec_loaded = False
    _db_attempted = False


def _graph() -> Optional[ResearchGraph]:
    global _graph_cache, _graph_attempted
    if not _graph_attempted:
        _graph_cache = ResearchGraph.load(RESEARCH_DIR)
        _graph_attempted = True
    return _graph_cache


def _db():
    global _db_conn, _db_vec_loaded, _db_attempted
    if not _db_attempted:
        _db_conn, _db_vec_loaded = open_ro(RESEARCH_DIR / "research.db")
        _db_attempted = True
    return _db_conn, _db_vec_loaded


def _no_db() -> dict:
    return {
        "error": "research.db not found",
        "research_dir": str(RESEARCH_DIR),
        "hint": "Recompile with the current CLI; older builds didn't ship a DB.",
    }


def _no_graph() -> dict:
    return {
        "error": "no compiled research context",
        "research_dir": str(RESEARCH_DIR),
        "hint": "Run /paper-compiler:build-research-context <paper-id> first.",
    }


@mcp.tool()
def paper_summary(paper_id: str) -> dict:
    """Return metadata and a list of implementation atoms defined or used by this paper."""
    g = _graph()
    if g is None:
        return _no_graph()
    return g.paper_summary(paper_id)


@mcp.tool()
def trace_dependency(component: str) -> dict:
    """Trace the dependency chain for an implementation component.

    component: one of "architecture", "loss", "dataset", "preprocessing",
               "evaluation", "baseline", "optimizer".
    Returns the ordered chain of papers + atoms + evidence span IDs.
    """
    g = _graph()
    if g is None:
        return _no_graph()
    return g.trace(component)


@mcp.tool()
def find_atom(query: str, limit: int = 5) -> list[dict]:
    """Semantic + BM25 search across implementation atoms."""
    g = _graph()
    if g is None:
        return [_no_graph()]
    return g.search_atoms(query, limit=limit)


@mcp.tool()
def get_evidence(atom_id: str) -> list[dict]:
    """Return all evidence spans backing an atom."""
    g = _graph()
    if g is None:
        return [_no_graph()]
    return g.evidence_for(atom_id)


@mcp.tool()
def list_missing_details() -> list[dict]:
    """Return the list of unresolved implementation questions."""
    g = _graph()
    if g is None:
        return [_no_graph()]
    return g.missing_details()


@mcp.tool()
def equation_lookup(symbol_or_keyword: str, limit: int = 10) -> list[dict]:
    """Find equations in the corpus whose LaTeX body matches a symbol or keyword.

    Phase 8: queries the populated ``equations`` table directly (previously
    a stub that read a never-written ``equations.json``). Returns at most
    ``limit`` entries, ordered by defining paper's rank (so target paper
    surfaces first). Each result carries ``equation_id``, ``paper_id``,
    ``paper_title``, ``section_id``, and verbatim ``latex``.
    """
    conn, _ = _db()
    if conn is None:
        return [_no_db()]
    return db_equation_lookup(conn, symbol_or_keyword, limit=limit)


@mcp.tool()
def compare_methods(atom_a: str, atom_b: str) -> dict:
    """Side-by-side evidence comparison of two implementation atoms."""
    g = _graph()
    if g is None:
        return _no_graph()
    return g.compare(atom_a, atom_b)


@mcp.tool()
def citation_neighbors(paper_id: str, role: Optional[str] = None) -> list[dict]:
    """Adjacent papers, optionally filtered by citation edge role."""
    g = _graph()
    if g is None:
        return [_no_graph()]
    return g.neighbors(paper_id, role=role)


@mcp.tool()
def graph_stats() -> dict:
    """Counts, depth reached, coverage, build manifest, version."""
    g = _graph()
    if g is None:
        return _no_graph()
    return g.stats()


@mcp.tool()
def query(
    q: str,
    mode: str = "auto",
    limit: int = 8,
    full: bool = False,
    rerank: bool = True,
) -> dict:
    """Unified retrieval entry point with local / global / hybrid routing.

    `mode`:
      - `"auto"` (default) — routes by query text. Broad/comparative
        questions ("survey latent world models") → `global`. Specific
        entity lookups ("what loss does JEPA use") → `local`. Mixed →
        `hybrid` (reciprocal-rank-fusion merge).
      - `"local"`  — hybrid chunk retrieval with a +0.15 boost for papers
        in the query's top community.
      - `"global"` — Microsoft-GraphRAG style: returns the top-3 community
        summaries plus a small bundle of representative atoms and chunks
        from each community's member papers. Use for thematic/landscape
        questions where no single chunk has the answer.
      - `"hybrid"` — RRF merge of local + global.

    `rerank=True` runs a cross-encoder over the returned chunks when
    `PAPER_COMPILER_RERANK_MODEL` is set (e.g. `BAAI/bge-reranker-v2-m3`).
    Lazy-loaded; no-op when unset.

    `full=False` (default) is snippet-first; pass `True` once you've
    narrowed chunk_ids to receive verbatim text.

    Returns `{mode, route, results | communities, ...}` — shape depends on
    the selected mode.
    """
    conn, vec = _db()
    if conn is None:
        return _no_db()
    return db_query(conn, vec, q, mode=mode, limit=limit, full=full, rerank=rerank)


@mcp.tool()
def route_query_only(q: str) -> str:
    """Return the mode that `query(q, mode='auto')` would pick. Diagnostic tool."""
    return db_route_query(q)


@mcp.tool()
def query_chunks(
    query: str,
    limit: int = 8,
    full: bool = False,
    max_per_paper: int = 2,
    kinds: Optional[list[str]] = None,
    prefer_kind: Optional[str] = None,
) -> dict:
    """Hybrid BM25 + sqlite-vec chunk search across target + neighborhood papers.

    Default is **snippet-first**: each result returns a 240-char `snippet` plus
    `chunk_id`, `paper_id`, `paper_title`, `section_id`, `chunk_kind`. Pass
    `full=True` to receive the verbatim `text` (use this only after you've
    narrowed down which chunk_ids you actually need).

    **kinds** (hard filter, default = all):
        `["prose"]`, `["table"]`, `["caption"]`, `["reference"]`,
        `["equation_block"]`, `["answer"]`, or any subset.

    **prefer_kind** (soft boost): when retrieving a mixed-kind result set,
    chunks matching `prefer_kind` receive a +0.3 score bump. Use this for
    "find hyperparameter values" → `prefer_kind="table"` style queries.

    Diversification: at most `max_per_paper` chunks from any single paper
    appear in the result. Phase 6: **every** chunk is indexed (the v0.2
    60% dropout is gone); retrieval filters/boosts on `chunk_kind` instead.

    Returns `{"results": [...], "truncated": bool}`.
    """
    conn, vec = _db()
    if conn is None:
        return _no_db()
    return db_query_chunks(
        conn,
        vec,
        query,
        limit=limit,
        full=full,
        max_per_paper=max_per_paper,
        kinds=kinds,
        prefer_kind=prefer_kind,
    )


@mcp.tool()
def paper_text(
    paper_id: str,
    section_type: Optional[str] = None,
    paragraph_ids: Optional[list] = None,
    chunk_ids: Optional[list] = None,
    full: bool = False,
) -> dict:
    """Return chunks of one paper grouped by section.

    Default is **snippet-first**: each paragraph entry has `paragraph_id`,
    `chunk_id`, and a 240-char `snippet`. Pass `full=True` to inline the
    verbatim `text`. Use `paragraph_ids` / `chunk_ids` to pull only specific
    paragraphs after seeing snippets.

    `section_type` ∈ {abstract, introduction, related_work, method, experiments,
    results, discussion, conclusion, appendix, other}.
    """
    conn, _ = _db()
    if conn is None:
        return _no_db()
    return db_paper_text(
        conn,
        paper_id,
        section_type=section_type,
        paragraph_ids=paragraph_ids,
        chunk_ids=chunk_ids,
        full=full,
    )


@mcp.tool()
def community_summary(community_id: int) -> dict:
    """Return the LLM-generated label + summary + paper/atom members for one community."""
    conn, _ = _db()
    if conn is None:
        return _no_db()
    return db_community_summary(conn, community_id)


@mcp.tool()
def list_communities() -> list[dict]:
    """Return every detected community (community_id, label, size). Cheap; safe to call first."""
    conn, _ = _db()
    if conn is None:
        return [_no_db()]
    return db_list_communities(conn)


@mcp.tool()
def graph_sql(sql: str, params: Optional[list] = None, limit: int = 100) -> dict:
    """Read-only SQL escape hatch over research.db.

    Only SELECT / WITH allowed; multiple statements rejected. Use this when the
    structured tools don't fit (custom joins, aggregates, debugging). See
    `schema_doc()` for table and column reference.
    """
    conn, _ = _db()
    if conn is None:
        return _no_db()
    return safe_sql(conn, sql, params=params, limit=limit)


@mcp.tool()
def schema_doc() -> str:
    """Return SCHEMA.md verbatim. Read this before writing custom SQL via `graph_sql`."""
    return schema_doc_text(RESEARCH_DIR)


@mcp.tool()
def neighborhood_subgraph(
    node_id: str,
    hops: int = 2,
    role_filter: Optional[str] = None,
    limit: int = 40,
) -> dict:
    """BFS-expand the graph around a paper or atom and return a labeled subgraph.

    Use this when "what's connected to X?" is the question, especially when the
    answer needs to span both citation edges and shared-atom usage. Returns:

    - `root`: the starting node ({id, kind: "paper" | "atom", label}).
    - `nodes`: all nodes reachable within `hops`.
    - `edges`: labeled edges. `kind` is one of `citation` / `has_atom` /
      `defines` / `uses_atom`; citations also carry `role` and `confidence`.
    - `via_atoms`: atoms shared by ≥2 papers in the subgraph (bridge nodes).
    - `truncated`: true if the result was capped by `limit`.

    Tips:
    - Start from an atom_id when you want all papers that use a specific
      method/loss/dataset.
    - Start from a paper_id when you want its citation neighborhood plus the
      atoms it defines/uses.
    - `role_filter` restricts citation edges to one PRD §12 label (e.g.
      `"loss_function_dependency"`).
    """
    g = _graph()  # ensures DB is opened; reuses cached conn below
    conn, _ = _db()
    if conn is None:
        return _no_db()
    return db_neighborhood_subgraph(conn, node_id, hops=hops, role_filter=role_filter, limit=limit)


@mcp.tool()
def shortest_path(
    from_id: str,
    to_id: str,
    max_hops: int = 4,
    k: int = 3,
    role_filter: Optional[str] = None,
) -> dict:
    """Return up to k shortest paths between two nodes (paper_ids or atom_ids).

    Use this when the question is "how is A related to B?". Returns 1–k paths
    ordered by total weight; each step lists the edge `role` (e.g.
    `architecture_dependency`, `uses_atom`, `defines`). Lower weight = stronger
    connection (`weight = 1 / confidence` for citation edges).

    `role_filter` is optional; when set, only citation edges with that role are
    considered.
    """
    conn, _ = _db()
    if conn is None:
        return _no_db()
    return db_shortest_paths(conn, from_id, to_id, max_hops=max_hops, k=k, role_filter=role_filter)


# --------------------------------------------------------------------------- #
# v2.0 — memory layer + runtime research-dir binding
# --------------------------------------------------------------------------- #


@mcp.tool()
def get_paper_context() -> dict:
    """Return a structured summary of the compiled paper context.

    Replaces the v0.x pattern of `Read research/research.md` at session start.
    Cheap one-call summary: paper title + id, atom counts by category,
    top-priority atoms, community count, missing-details count, recent
    session count, recent decisions count.

    Skills should call this FIRST when starting any implementation work — it
    gives Claude enough context to pick the right sub-skill without reading
    the brief directly.
    """
    g = _graph()
    if g is None:
        return _no_graph()
    research_dir = _research_dir()

    stats = g.stats()
    # Counts by category, sorted high → low.
    by_cat: dict[str, int] = {}
    for a in g.atoms.values():
        c = a.get("category") or "uncategorized"
        by_cat[c] = by_cat.get(c, 0) + 1
    cat_breakdown = sorted(by_cat.items(), key=lambda kv: -kv[1])

    # Top-priority atoms (up to 10).
    top_atoms = sorted(
        g.atoms.values(),
        key=lambda a: -(a.get("priority") or 0),
    )[:10]
    top_atoms_out = [
        {
            "atom_id": a["id"],
            "uid": a.get("uid"),
            "name": a["name"],
            "category": a["category"],
            "subcategory": a.get("subcategory"),
            "priority": a.get("priority"),
        }
        for a in top_atoms
    ]

    # Sessions + decisions on disk (the memory layer).
    sessions_list = sessions_mod.list_files(research_dir / "sessions", limit=3)
    decisions_file = research_dir / "decisions.md"
    decisions_count = len(decisions_mod.parse_file(decisions_file))

    return {
        "research_dir": str(research_dir),
        "schema_version": stats.get("schema_version"),
        "compiled_at": stats.get("compiled_at"),
        "target_paper_id": stats.get("target_paper_id"),
        "title": (g.papers.get(stats.get("target_paper_id"), {}).get("metadata") or {}).get("title"),
        "counts": {
            "papers": stats.get("papers", 0),
            "atoms": stats.get("atoms", 0),
            "evidence_spans": stats.get("evidence_spans", 0),
            "edges": stats.get("edges", 0),
            "missing_details": stats.get("missing_details", 0),
        },
        "atoms_by_category": [{"category": c, "count": n} for c, n in cat_breakdown],
        "top_atoms": top_atoms_out,
        "memory": {
            "recent_sessions": sessions_list,
            "total_decisions": decisions_count,
        },
        "hints": _routing_hints(by_cat),
    }


def _routing_hints(by_cat: dict[str, int]) -> list[str]:
    """Tiny per-corpus routing tips based on which categories have atoms.

    Cheap heuristic — no LLM. Just helps Claude pick the right sub-skill
    without re-asking the user "what category is this?".
    """
    hints: list[str] = []
    if by_cat.get("method", 0) >= 5:
        hints.append("Method atoms are dense — start with `/paper-compiler:use-research-context implement-method`.")
    if by_cat.get("objective", 0) >= 1:
        hints.append("Objective atoms present — `implement-objective` covers loss / Hamiltonian / yield / fitness.")
    if by_cat.get("procedure", 0) >= 3:
        hints.append("Procedure / parameter atoms present — `implement-procedure` covers training loop / integrator / experimental protocol.")
    if by_cat.get("theory", 0) >= 1:
        hints.append("Theory atoms present — verify assumptions/preconditions hold in implementation.")
    if not hints:
        hints.append("Mixed corpus — run `route_query_only(your_question)` to pick the right retrieval mode.")
    return hints


@mcp.tool()
def list_sessions(limit: int = 5) -> list[dict]:
    """List the most recent session notes from `research/sessions/`.

    Each session is one markdown file written by the Stop hook at session
    end. Returns newest first. Each entry: `{session_id, date, slug, path,
    atoms_touched, has_next_steps}`. Use `resume_session(session_id)` to
    read one in full.
    """
    return sessions_mod.list_files(_research_dir() / "sessions", limit=int(limit))


@mcp.tool()
def resume_session(session_id: str) -> dict:
    """Read one session note in full.

    Returns: title, started/ended timestamps, paper, atoms_touched,
    files_modified, decisions_recorded, next_steps. Used by the `continue`
    sub-skill and `resume-session` top-level skill to reconstruct state.
    """
    path = _research_dir() / "sessions" / f"{session_id}.md"
    parsed = sessions_mod.parse_file(path)
    if parsed is None:
        return {"error": f"session {session_id!r} not found at {path}"}
    return parsed


@mcp.tool()
def get_decisions_since(since: str = "") -> list[dict]:
    """Read entries from `research/decisions.md` since `since` (ISO date or timestamp).

    Pass empty string to get all entries. Each entry: `{timestamp, slug,
    body: {category, atom, decision, why, source, ...}, raw}`. The decision
    log is the cross-session memory layer — past gotchas, failed approaches,
    and load-bearing choices live here.
    """
    return decisions_mod.get_since(_research_dir() / "decisions.md", since)


@mcp.tool()
def record_decision(
    category: str,
    decision: str,
    why: str,
    atom_uid: Optional[str] = None,
    source_chunk_id: Optional[int] = None,
    source_paper_id: Optional[str] = None,
    slug_hint: Optional[str] = None,
) -> dict:
    """Append a structured entry to `research/decisions.md`.

    **Write tool — requires user approval (gated via .claude/settings.json
    `ask` list).** Use for load-bearing choices that future sessions need to
    see: defaults adopted when the paper is silent, ambiguities resolved one
    way vs another, approaches tried that didn't work.

    `category` should match an atom category (`method`, `objective`, `data`,
    `procedure`, `parameter`, `evaluation`, `baseline`, `theory`).
    `atom_uid` is the Phase-1 stable identifier (16 hex chars); pass it when
    the decision is about a specific atom.
    `slug_hint` controls the URL-friendly suffix (e.g. "loss-form",
    "sampling-collapse"); auto-derived from the first few decision words if
    omitted.
    """
    return decisions_mod.append_entry(
        _research_dir() / "decisions.md",
        category=category,
        decision=decision,
        why=why,
        atom_uid=atom_uid,
        source_chunk_id=source_chunk_id,
        source_paper_id=source_paper_id,
        slug_hint=slug_hint,
    )


@mcp.tool()
def append_session_note(
    note: str,
    kind: str = "atom_touched",
    session_id: Optional[str] = None,
) -> dict:
    """Append a one-line note to a session file.

    **Write tool — requires user approval (gated via .claude/settings.json
    `ask` list).** Used by the Stop hook and by the `continue` sub-skill to
    drop atoms/files/decisions/next-steps into the running session note.

    `kind` ∈ {`atom_touched`, `file_modified`, `decision_referenced`,
    `next_step`}. `session_id` selects which session file (filename without
    .md); omitted = newest. If no session file exists, creates an adhoc one
    for today.
    """
    return sessions_mod.append_note(
        _research_dir() / "sessions",
        session_id=session_id,
        note=note,
        kind=kind,
    )


@mcp.tool()
def bind_research_dir(path: str) -> dict:
    """Rebind the MCP server's active research directory at runtime.

    Used by `/paper-compiler:compare-corpora` to flip between two compiled
    artifacts in one session, and by `/paper-compiler:use-research-context
    port` to re-bind after copying an artifact into a new repo.

    The new path must contain a `build-manifest.json`; otherwise the bind
    is rejected and the previous binding stays. Validates and invalidates
    the graph + DB caches so subsequent calls re-load.

    **Serial only.** Two concurrent compare-corpora calls would corrupt the
    shared bound dir. Document at the call site.
    """
    global RESEARCH_DIR
    new_path = Path(path).expanduser().resolve()
    if not new_path.exists():
        return {"ok": False, "reason": f"path does not exist: {new_path}"}
    manifest = new_path / "build-manifest.json"
    if not manifest.exists():
        return {
            "ok": False,
            "reason": f"no build-manifest.json at {new_path} — does this look like a compiled research/ artifact?",
        }
    old_path = str(RESEARCH_DIR)
    RESEARCH_DIR = new_path
    _invalidate_caches()
    title = None
    paper_id = None
    try:
        meta = json.loads(manifest.read_text(encoding="utf-8"))
        title = meta.get("title")
        paper_id = meta.get("target_paper_id")
    except Exception:  # noqa: BLE001
        pass
    return {
        "ok": True,
        "previous": old_path,
        "current": str(new_path),
        "paper_title": title,
        "paper_id": paper_id,
    }


if __name__ == "__main__":
    mcp.run()
