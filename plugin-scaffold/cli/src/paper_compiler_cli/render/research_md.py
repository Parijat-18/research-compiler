from __future__ import annotations

from typing import Any

from ..atoms import Atom
from ..config import Config
from ..ir import Paper

try:
    import tiktoken

    _ENC = tiktoken.get_encoding("cl100k_base")

    def _count(text: str) -> int:
        return len(_ENC.encode(text))

except Exception:  # noqa: BLE001
    def _count(text: str) -> int:
        return max(1, int(len(text) / 4))


CATEGORY_HEADINGS = (
    # Domain-neutral. Each heading shows in any paper's brief regardless
    # of field; an ML paper, a physics simulation paper, and a chemistry
    # methods paper all use the same skeleton.
    ("data", "Data / measurements"),
    ("preprocessing", "Preprocessing"),
    ("method", "Method / algorithm"),
    ("objective", "Objective / function being optimized or measured"),
    ("procedure", "Procedure (training / simulation / experimental protocol)"),
    ("parameter", "Parameters / settings"),
    ("evaluation", "Evaluation"),
    ("baseline", "Baselines"),
    ("theory", "Theoretical assumptions / theorems"),
)


def _atom_block(atom: Atom, graph: dict[str, Any]) -> str:
    defining = graph["papers"].get(atom.defined_by_paper_id, {})
    defining_title = (defining.get("metadata") or {}).get("title", "self")
    evidence_files = [f"research/evidence/{e}.md" for e in atom.evidence_span_ids[:2]]
    block = [
        f"### {atom.name} (`{atom.id}` · {atom.category})",
        f"- **Defined by:** {defining_title} (`{atom.defined_by_paper_id}`)",
        f"- **Description:** {atom.description[:300]}",
    ]
    if evidence_files:
        block.append(f"- **Evidence:** {', '.join(evidence_files)}")
    if atom.equation_refs:
        block.append(f"- **Equations:** {atom.equation_refs}")
    return "\n".join(block)


def _tldr(target: Paper, atoms: list[Atom]) -> str:
    n_atoms = len(atoms)
    categories = sorted({a.category for a in atoms})
    bullets = [
        f"- Target paper: **{target.metadata.title}** ({target.metadata.year}).",
        f"- {n_atoms} implementation atoms across {len(categories)} categories: {', '.join(categories)}.",
        "- Read this brief, then call `mcp__paper-compiler__*` for specifics. Do not rely on model memory for paper-specific details.",
    ]
    if target.metadata.abstract:
        bullets.append(f"- Abstract excerpt: {target.metadata.abstract[:400]}")
    return "\n".join(bullets)


def render_research_md(
    cfg: Config,
    target: Paper,
    graph: dict[str, Any],
    atoms: list[Atom],
    order: list[dict],
) -> str:
    parts: list[str] = []
    parts.append(f"# Research Brief: {target.metadata.title}\n")
    parts.append("## TL;DR\n" + _tldr(target, atoms) + "\n")
    parts.append("## Paper identity\n")
    ids = target.external_ids.model_dump(exclude_none=True)
    parts.append(f"- Authors: {', '.join(a.name for a in target.metadata.authors)}")
    parts.append(f"- Year: {target.metadata.year} · Venue: {target.metadata.venue or 'n/a'}")
    parts.append(f"- IDs: {ids}")
    parts.append(f"- S2 paper ID: `{target.paper_id}`\n")

    parts.append("## What we're implementing\n")
    parts.append("Components below are extracted from the paper's method/procedure sections and linked to defining papers in the citation neighborhood. The plugin is domain-neutral — categories cover ML, physics, chemistry, biology, and any field with implementable methods. Query the MCP server for any specific decision.\n")

    parts.append("## Implementation atoms\n")
    by_cat: dict[str, list[Atom]] = {}
    for a in atoms:
        by_cat.setdefault(a.category, []).append(a)

    for cat, heading in CATEGORY_HEADINGS:
        if cat not in by_cat:
            continue
        parts.append(f"### {heading}\n")
        for atom in sorted(by_cat[cat], key=lambda x: -x.priority):
            parts.append(_atom_block(atom, graph) + "\n")

    parts.append("## Suggested implementation order\n")
    for i, item in enumerate(order[:25], 1):
        a = next((x for x in atoms if x.id == item["atom_id"]), None)
        if a:
            parts.append(f"{i}. `{a.id}` — {a.name} ({a.category})")
    parts.append("")

    parts.append("## Where to query the graph instead of guessing\n")
    parts.append("- Method / algorithm: `mcp__paper-compiler__trace_dependency` component=method")
    parts.append("- Objective: `trace_dependency` component=objective")
    parts.append("- Data / preprocessing: `trace_dependency` component=data|preprocessing")
    parts.append("- Procedure (training / simulation / protocol): `trace_dependency` component=procedure")
    parts.append("- Evaluation: `trace_dependency` component=evaluation")
    parts.append("- Baselines: `trace_dependency` component=baseline")
    parts.append("- Theory: `trace_dependency` component=theory")
    parts.append("- Any atom: `find_atom(query)` → `get_evidence(atom_id)`")
    parts.append("- Open assumptions: `list_missing_details()`\n")

    md = "\n".join(parts)
    budget = cfg.output.research_md_max_tokens
    tokens = _count(md)
    if tokens > budget:
        truncated_atoms = sorted(atoms, key=lambda a: a.priority)
        while tokens > budget and truncated_atoms:
            victim = truncated_atoms.pop(0)
            md = md.replace(_atom_block(victim, graph) + "\n", f"_(omitted: `{victim.id}` — see `research/evidence/`)_\n")
            tokens = _count(md)
        if tokens > budget:
            md = md[: budget * 4] + "\n\n_(brief truncated to token budget; remaining atoms in `graph.json`.)_\n"
    return md
