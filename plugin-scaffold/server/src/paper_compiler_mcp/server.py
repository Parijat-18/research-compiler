"""
paper-compiler MCP server (v0.1 scaffold)

This is a STUB. It returns hardcoded responses so the plugin wiring can be tested
end-to-end before the real graph and indexes are implemented.

Real implementation: load research/graph.json on first tool call and route every
tool through the in-memory ResearchGraph object. See docs/04-architecture.md.
"""

import json
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

RESEARCH_DIR = Path(os.environ.get("PAPER_COMPILER_RESEARCH_DIR", "./research"))
GRAPH_PATH = RESEARCH_DIR / "graph.json"

mcp = FastMCP("paper-compiler")


def _load_graph() -> dict:
    """Lazy-load graph.json. Returns {} if not present (scaffold mode)."""
    if not GRAPH_PATH.exists():
        return {}
    try:
        return json.loads(GRAPH_PATH.read_text())
    except json.JSONDecodeError:
        return {}


_graph_cache: dict | None = None


def _graph() -> dict:
    global _graph_cache
    if _graph_cache is None:
        _graph_cache = _load_graph()
    return _graph_cache


# ---------------------------------------------------------------------------
# Tools (stubs — see docs/04-architecture.md §5 for the real schema and
# docs/01-PRD.md §13 for the surface contract.)
# ---------------------------------------------------------------------------


@mcp.tool()
def paper_summary(paper_id: str) -> dict:
    """Return metadata and a list of implementation atoms defined or used by this paper."""
    g = _graph()
    if not g:
        return {"_scaffold": True, "message": "graph.json not found; run /paper-compiler:build-research-context first."}
    return g.get("papers", {}).get(paper_id, {"error": f"paper {paper_id} not in graph"})


@mcp.tool()
def trace_dependency(component: str) -> dict:
    """
    Trace the dependency chain for an implementation component.

    component: one of "architecture", "loss", "dataset", "preprocessing",
               "evaluation", "baseline", "optimizer".
    """
    valid = {"architecture", "loss", "dataset", "preprocessing", "evaluation", "baseline", "optimizer"}
    if component not in valid:
        return {"error": f"unknown component {component!r}; expected one of {sorted(valid)}"}
    g = _graph()
    if not g:
        return {"_scaffold": True, "component": component, "chain": []}
    # TODO: implement
    return {"component": component, "chain": [], "_note": "not implemented yet"}


@mcp.tool()
def find_atom(query: str, limit: int = 5) -> list[dict]:
    """Semantic + BM25 search across implementation atoms."""
    g = _graph()
    if not g:
        return [{"_scaffold": True}]
    # TODO: implement
    return []


@mcp.tool()
def get_evidence(atom_id: str) -> list[dict]:
    """Return all evidence spans backing an atom."""
    g = _graph()
    if not g:
        return [{"_scaffold": True, "atom_id": atom_id}]
    # TODO: implement
    return []


@mcp.tool()
def list_missing_details() -> list[dict]:
    """Return the list of unresolved implementation questions."""
    g = _graph()
    if not g:
        return [{"_scaffold": True}]
    return g.get("missing_details", [])


@mcp.tool()
def equation_lookup(symbol_or_keyword: str) -> list[dict]:
    """Find equations across the compiled corpus that match a symbol or keyword."""
    g = _graph()
    if not g:
        return [{"_scaffold": True}]
    # TODO: implement
    return []


@mcp.tool()
def compare_methods(atom_a: str, atom_b: str) -> dict:
    """Side-by-side evidence comparison of two implementation atoms."""
    g = _graph()
    if not g:
        return {"_scaffold": True, "a": atom_a, "b": atom_b}
    # TODO: implement
    return {"a": atom_a, "b": atom_b, "comparison": [], "_note": "not implemented yet"}


@mcp.tool()
def citation_neighbors(paper_id: str, role: str | None = None) -> list[dict]:
    """Adjacent papers, optionally filtered by citation edge role."""
    g = _graph()
    if not g:
        return [{"_scaffold": True, "paper_id": paper_id}]
    # TODO: implement
    return []


@mcp.tool()
def graph_stats() -> dict:
    """Counts, depth reached, coverage, build manifest, version."""
    g = _graph()
    if not g:
        return {
            "_scaffold": True,
            "research_dir": str(RESEARCH_DIR),
            "graph_loaded": False,
            "message": "No compiled research context found. Run /paper-compiler:build-research-context <id>.",
        }
    return {
        "schema_version": g.get("schema_version"),
        "compiled_at": g.get("compiled_at"),
        "target_paper_id": g.get("target_paper_id"),
        "papers": len(g.get("papers", {})),
        "atoms": len(g.get("atoms", {})),
        "evidence_spans": len(g.get("evidence", {})),
        "edges": len(g.get("edges", {})),
        "build_stats": g.get("build_stats", {}),
    }


if __name__ == "__main__":
    mcp.run()
