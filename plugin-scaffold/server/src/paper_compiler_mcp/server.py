"""paper-compiler MCP server.

Reads research/graph.json compiled by the CLI and exposes the nine query tools
described in docs/01-PRD.md §13. Graph is loaded lazily on the first tool call
so import is fast (per docs/03-claude-code-plugin-guide.md §11).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

from .db import (
    community_summary as db_community_summary,
    list_communities as db_list_communities,
    neighborhood_subgraph as db_neighborhood_subgraph,
    open_ro,
    paper_text as db_paper_text,
    query_chunks as db_query_chunks,
    safe_sql,
    schema_doc_text,
    shortest_paths as db_shortest_paths,
)
from .graph import ResearchGraph

RESEARCH_DIR = Path(os.environ.get("PAPER_COMPILER_RESEARCH_DIR", "./research"))
mcp = FastMCP("paper-compiler")

_graph_cache: Optional[ResearchGraph] = None
_graph_attempted = False

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
def equation_lookup(symbol_or_keyword: str) -> list[dict]:
    """Find equations across the compiled corpus that match a symbol or keyword."""
    g = _graph()
    if g is None:
        return [_no_graph()]
    return g.find_equation(symbol_or_keyword)


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
def query_chunks(query: str, limit: int = 8, full: bool = False, max_per_paper: int = 2) -> dict:
    """Hybrid BM25 + sqlite-vec chunk search across target + neighborhood papers.

    Default is **snippet-first**: each result returns a 240-char `snippet` plus
    `chunk_id`, `paper_id`, `paper_title`, `section_id`. Pass `full=True` to
    receive the verbatim `text` (use this only after you've narrowed down which
    chunk_ids you actually need).

    Diversification: at most `max_per_paper` chunks from any single paper appear
    in the result, so one mega-paper can't crowd out the rest. Index excludes
    table / figure-caption / non-prose chunks (`is_indexed = 0`).

    Returns `{"results": [...], "truncated": bool}`.
    """
    conn, vec = _db()
    if conn is None:
        return _no_db()
    return db_query_chunks(conn, vec, query, limit=limit, full=full, max_per_paper=max_per_paper)


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


if __name__ == "__main__":
    mcp.run()
