"""llm-wiki style article generator.

Karpathy's /raw → llm-wiki pattern, scoped to one paper compile. Three article
types, each with [[wikilink]] cross-references so an LLM (or a human in
Obsidian) can navigate by clicking:

    research/wiki/index.md
    research/wiki/atoms/<atom-id>.md         (per implementation atom)
    research/wiki/papers/<safe-paper-id>.md  (per neighborhood paper)
    research/wiki/communities/<n>.md         (per detected community)

All articles are also indexed in `chunks` + `chunks_fts` so the MCP server can
serve them via the same query surface as the source-paper text.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..atoms import Atom, EvidenceSpan
from ..communities import Community


def _safe(pid: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", pid)


def _atom_link(atom: Atom) -> str:
    # atom.id is already "atom-001", don't double-prefix.
    return f"[[{atom.id}|{atom.name}]]"


def _paper_link(paper_id: str, papers: dict[str, dict]) -> str:
    rec = papers.get(paper_id) or {}
    title = (rec.get("metadata") or {}).get("title", paper_id)
    return f"[[paper-{_safe(paper_id)}|{title}]]"


def render_atom_article(atom: Atom, papers: dict[str, dict], evidence_by_id: dict[str, EvidenceSpan], related: list[Atom]) -> str:
    rec = (papers.get(atom.defined_by_paper_id) or {}).get("metadata") or {}
    defining_title = rec.get("title") or atom.defined_by_paper_id
    body: list[str] = []
    body.append(f"# {atom.name}\n")
    body.append(f"- **Category:** `{atom.category}`")
    body.append(f"- **Atom ID:** `{atom.id}`")
    body.append(f"- **Defined by:** {_paper_link(atom.defined_by_paper_id, papers)}  · *{defining_title}*")
    body.append(f"- **Priority:** {atom.priority:.2f}")
    if atom.dependencies:
        body.append("- **Depends on:** " + ", ".join(f"[[atom-{d}]]" for d in atom.dependencies))
    body.append("")
    body.append("## Description")
    body.append(atom.description or "_no description extracted_")
    body.append("")

    if atom.evidence_span_ids:
        body.append("## Evidence")
        for eid in atom.evidence_span_ids:
            ev = evidence_by_id.get(eid)
            if not ev:
                continue
            body.append(f"### `{ev.id}` (paper {_paper_link(ev.paper_id, papers)} · section `{ev.section_id}` · {ev.section_type})")
            body.append("> " + (ev.verbatim_text or "").replace("\n", "\n> "))
            body.append("")

    if related:
        body.append("## Related atoms")
        for r in related[:8]:
            body.append(f"- {_atom_link(r)} (`{r.category}`)")
        body.append("")

    body.append("## Query")
    body.append(f"- `mcp__paper-compiler__get_evidence(atom_id=\"{atom.id}\")`")
    body.append(f"- `mcp__paper-compiler__find_atom(query=\"{atom.name[:60]}\")`")
    return "\n".join(body) + "\n"


def render_paper_article(paper_id: str, papers: dict[str, dict], atoms: list[Atom], edges: list[dict]) -> str:
    rec = papers.get(paper_id) or {}
    md = rec.get("metadata") or {}
    body: list[str] = []
    body.append(f"# {md.get('title', paper_id)}\n")
    authors = md.get("authors") or []
    author_names: list[str] = []
    for a in authors[:10]:
        if isinstance(a, str):
            author_names.append(a)
        elif isinstance(a, dict):
            author_names.append(a.get("name") or "")
    author_names = [n for n in author_names if n]
    if author_names:
        body.append("**Authors:** " + ", ".join(author_names))
    if md.get("year"):
        body.append(f"**Year:** {md['year']}")
    body.append(f"**Paper ID:** `{paper_id}`")
    if rec.get("rank") is not None:
        body.append(f"**Rank:** {rec['rank']:.2f}  ·  Impl. influence: {rec.get('implementation_influence', 0):.2f}")
    body.append("")
    if md.get("abstract"):
        body.append("## Abstract")
        body.append(md["abstract"])
        body.append("")

    defines = [a for a in atoms if a.defined_by_paper_id == paper_id]
    uses = [a for a in atoms if paper_id in a.used_by_paper_ids and a.defined_by_paper_id != paper_id]
    if defines:
        body.append("## Atoms defined here")
        for a in defines:
            body.append(f"- {_atom_link(a)} (`{a.category}`)")
        body.append("")
    if uses:
        body.append("## Atoms used by this paper")
        for a in uses:
            body.append(f"- {_atom_link(a)} (`{a.category}`)")
        body.append("")

    incoming = [e for e in edges if e["to_paper_id"] == paper_id]
    outgoing = [e for e in edges if e["from_paper_id"] == paper_id]
    if incoming:
        body.append("## Cited by")
        for e in incoming[:20]:
            other = e["from_paper_id"]
            body.append(f"- {_paper_link(other, papers)} · *{e.get('best_role')}* (conf {e.get('best_confidence', 0):.2f})")
        body.append("")
    if outgoing:
        body.append("## Cites")
        for e in outgoing[:20]:
            other = e["to_paper_id"]
            body.append(f"- {_paper_link(other, papers)} · *{e.get('best_role')}* (conf {e.get('best_confidence', 0):.2f})")
        body.append("")

    body.append("## Query")
    body.append(f"- `mcp__paper-compiler__paper_summary(paper_id=\"{paper_id}\")`")
    body.append(f"- `mcp__paper-compiler__citation_neighbors(paper_id=\"{paper_id}\")`")
    return "\n".join(body) + "\n"


def render_community_article(c: Community, papers: dict[str, dict], atoms_by_id: dict[str, Atom]) -> str:
    body: list[str] = []
    body.append(f"# {c.label}  *(community {c.id})*\n")
    if c.summary:
        body.append("## Summary")
        body.append(c.summary)
        body.append("")
    body.append(f"**Size:** {c.size} papers · {len(c.atom_ids)} atoms")
    body.append("")

    body.append("## Papers")
    for pid in c.paper_ids[:30]:
        body.append(f"- {_paper_link(pid, papers)}")
    body.append("")

    if c.atom_ids:
        body.append("## Atoms")
        for aid in c.atom_ids[:30]:
            a = atoms_by_id.get(aid)
            if a:
                body.append(f"- {_atom_link(a)} (`{a.category}`)")
        body.append("")

    body.append("## Query")
    body.append(f"- `mcp__paper-compiler__community_summary(community_id={c.id})`")
    return "\n".join(body) + "\n"


def render_index(papers: dict[str, dict], atoms: list[Atom], communities: list[Community]) -> str:
    body: list[str] = []
    body.append("# Research Wiki — index\n")
    body.append("This wiki is a navigable view of the compiled research context. Every link is an `[[obsidian-style]]` wikilink to another article. Articles are also indexed in `research/research.db` for hybrid BM25 + vector retrieval via the MCP server.\n")

    if communities:
        body.append("## Communities")
        for c in communities[:20]:
            body.append(f"- [[community-{c.id}|{c.label}]] — {c.size} papers, {len(c.atom_ids)} atoms")
        body.append("")

    body.append("## Atoms by category")
    by_cat: dict[str, list[Atom]] = {}
    for a in atoms:
        by_cat.setdefault(a.category, []).append(a)
    for cat in sorted(by_cat):
        body.append(f"### {cat}")
        for a in sorted(by_cat[cat], key=lambda x: -x.priority):
            body.append(f"- {_atom_link(a)}")
        body.append("")

    body.append("## Top papers (by implementation influence)")
    sortable = [(pid, rec) for pid, rec in papers.items() if rec.get("implementation_influence") is not None]
    sortable.sort(key=lambda kv: -float(kv[1].get("implementation_influence") or 0))
    for pid, rec in sortable[:25]:
        title = (rec.get("metadata") or {}).get("title", pid)
        body.append(f"- {_paper_link(pid, papers)} — impl {rec.get('implementation_influence', 0):.2f}")
    return "\n".join(body) + "\n"


def write_wiki(
    wiki_dir: Path,
    papers: dict[str, dict],
    atoms: list[Atom],
    evidence: list[EvidenceSpan],
    edges: list[dict],
    communities: list[Community],
) -> int:
    wiki_dir.mkdir(parents=True, exist_ok=True)
    (wiki_dir / "atoms").mkdir(exist_ok=True)
    (wiki_dir / "papers").mkdir(exist_ok=True)
    (wiki_dir / "communities").mkdir(exist_ok=True)

    evidence_by_id = {e.id: e for e in evidence}
    atoms_by_id = {a.id: a for a in atoms}

    # Build a related-atoms map: same category + shared defining paper.
    related_by_id: dict[str, list[Atom]] = {}
    by_category: dict[str, list[Atom]] = {}
    for a in atoms:
        by_category.setdefault(a.category, []).append(a)
    for a in atoms:
        siblings = [b for b in by_category[a.category] if b.id != a.id]
        related_by_id[a.id] = siblings[:6]

    n = 0
    for a in atoms:
        # a.id is already "atom-001"; the directory is "atoms/" so we just use the id.
        path = wiki_dir / "atoms" / f"{a.id}.md"
        path.write_text(render_atom_article(a, papers, evidence_by_id, related_by_id[a.id]))
        n += 1
    for pid, rec in papers.items():
        path = wiki_dir / "papers" / f"paper-{_safe(pid)}.md"
        path.write_text(render_paper_article(pid, papers, atoms, edges))
        n += 1
    for c in communities:
        path = wiki_dir / "communities" / f"community-{c.id}.md"
        path.write_text(render_community_article(c, papers, atoms_by_id))
        n += 1
    # Karpathy-style answers dir (created empty here; wiki-query writes into it).
    (wiki_dir / "answers").mkdir(exist_ok=True)
    (wiki_dir / "index.md").write_text(render_index(papers, atoms, communities))
    return n + 1
