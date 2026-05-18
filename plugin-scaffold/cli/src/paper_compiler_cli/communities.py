"""Community detection + LLM summarization for the implementation atom graph.

Builds a NetworkX graph from atoms + edges (papers as nodes, atoms as attribute
groups), runs greedy modularity / Louvain, then asks the LLM to label and
summarize each community in 2-4 sentences. Mirrors GraphRAG's community-report
abstraction but scoped to one paper's neighborhood.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Optional

from .atoms import Atom
from .classify.edge import ClassifiedEdge
from .config import Config
from .llm import call_llm, parse_json_object


@dataclass
class Community:
    id: int
    paper_ids: list[str]
    atom_ids: list[str]
    label: str
    summary: str
    size: int


def _build_graph(atoms: list[Atom], edges: list[ClassifiedEdge]):
    try:
        import networkx as nx
    except ImportError:
        return None
    g = nx.Graph()
    paper_to_atoms: dict[str, list[Atom]] = {}
    for a in atoms:
        g.add_node(a.defined_by_paper_id, kind="paper")
        paper_to_atoms.setdefault(a.defined_by_paper_id, []).append(a)
        for pid in a.used_by_paper_ids:
            g.add_node(pid, kind="paper")

    def _bump(u: str, v: str, w: float) -> None:
        if not u or not v or u == v:
            return
        if g.has_edge(u, v):
            g[u][v]["weight"] = float(g[u][v]["weight"]) + w
        else:
            g.add_edge(u, v, weight=w)

    # Strong: classified citation edges (paper cites paper, with implementation role).
    for ce in edges:
        w = ce.roles[0].confidence if ce.roles else 0.1
        _bump(ce.edge.from_paper_id, ce.edge.to_paper_id, float(w))

    # Weak: paper P defines an atom that paper Q uses → "uses-this-atom" edge.
    for a in atoms:
        d = a.defined_by_paper_id
        for q in a.used_by_paper_ids:
            if q != d:
                _bump(d, q, 0.3)

    # Weakest: two papers share ≥2 atoms in the same category → topical co-occurrence.
    by_paper: dict[str, dict[str, set[str]]] = {}
    for a in atoms:
        for q in a.used_by_paper_ids:
            by_paper.setdefault(q, {}).setdefault(a.category, set()).add(a.id)
    paper_ids = list(by_paper)
    for i in range(len(paper_ids)):
        for j in range(i + 1, len(paper_ids)):
            p1, p2 = paper_ids[i], paper_ids[j]
            shared_cats = sum(
                1
                for cat in by_paper[p1]
                if cat in by_paper[p2] and len(by_paper[p1][cat] & by_paper[p2][cat]) >= 2
            )
            if shared_cats >= 1:
                _bump(p1, p2, 0.2 * shared_cats)

    return g, paper_to_atoms


def _detect(g) -> list[set]:
    # Prefer Louvain with resolution > 1 so we don't collapse into one mega-cluster.
    try:
        from networkx.algorithms.community import louvain_communities

        return list(louvain_communities(g, weight="weight", resolution=1.4, seed=42))
    except Exception as e:  # noqa: BLE001
        print(f"louvain failed ({e}); falling back to greedy modularity", file=sys.stderr)
    try:
        from networkx.algorithms.community import greedy_modularity_communities

        return list(greedy_modularity_communities(g, weight="weight"))
    except Exception as e:  # noqa: BLE001
        print(f"community detection failed: {e}", file=sys.stderr)
        return [set(g.nodes())]


def _summarize_llm(cfg: Config, papers_meta: list[dict], atoms_meta: list[dict]) -> tuple[str, str]:
    system = (
        "You label and summarize a community of research papers + extracted "
        'implementation atoms. Return JSON: {"label": "<2-5 word community name>", '
        '"summary": "<2-4 sentence summary of the shared theme>"}.'
    )
    payload = {
        "papers": [{"title": p["title"], "year": p.get("year"), "abstract": (p.get("abstract") or "")[:300]} for p in papers_meta[:8]],
        "atoms": [{"name": a["name"], "category": a["category"], "description": (a.get("description") or "")[:120]} for a in atoms_meta[:10]],
    }
    import json

    result = call_llm(cfg, system, json.dumps(payload), max_tokens=240)
    if result is None:
        title = (papers_meta[0]["title"] if papers_meta else "Cluster")[:40]
        return f"Cluster around {title}", "LLM unavailable; community summary skipped."
    data = parse_json_object(result.text) or {}
    return (data.get("label") or "Community")[:60], (data.get("summary") or "")[:600]


def detect_and_summarize(
    cfg: Config,
    atoms: list[Atom],
    edges: list[ClassifiedEdge],
    paper_records: dict[str, dict],
    max_llm_calls: int = 12,
) -> list[Community]:
    res = _build_graph(atoms, edges)
    if res is None:
        return []
    g, paper_to_atoms = res
    if g.number_of_nodes() == 0:
        return []
    detected = _detect(g)
    out: list[Community] = []
    llm_budget = max_llm_calls
    for cid, members in enumerate(sorted(detected, key=len, reverse=True)):
        if len(members) < 2:
            continue
        paper_ids = sorted(members)
        atom_ids = sorted({a.id for pid in paper_ids for a in paper_to_atoms.get(pid, [])})
        papers_meta = [
            {
                "paper_id": pid,
                "title": paper_records.get(pid, {}).get("title", ""),
                "year": paper_records.get(pid, {}).get("year"),
                "abstract": paper_records.get(pid, {}).get("abstract"),
            }
            for pid in paper_ids
        ]
        atoms_meta = [
            {"name": a.name, "category": a.category, "description": a.description}
            for pid in paper_ids
            for a in paper_to_atoms.get(pid, [])
        ]
        if llm_budget > 0 and (papers_meta or atoms_meta):
            label, summary = _summarize_llm(cfg, papers_meta, atoms_meta)
            llm_budget -= 1
        else:
            label = f"Community {cid}"
            summary = ""
        out.append(
            Community(
                id=cid,
                paper_ids=paper_ids,
                atom_ids=atom_ids,
                label=label,
                summary=summary,
                size=len(paper_ids),
            )
        )
    print(f"communities: detected {len(out)} (with summaries)", file=sys.stderr)
    return out


def ingest_communities(conn, communities: list[Community]) -> None:
    cur = conn.cursor()
    cur.execute("DELETE FROM community_papers")
    cur.execute("DELETE FROM community_atoms")
    cur.execute("DELETE FROM communities")
    for c in communities:
        cur.execute(
            "INSERT INTO communities(community_id, label, summary, size) VALUES (?,?,?,?)",
            (c.id, c.label, c.summary, c.size),
        )
        for pid in c.paper_ids:
            cur.execute("INSERT OR IGNORE INTO community_papers(community_id, paper_id) VALUES (?,?)", (c.id, pid))
        for aid in c.atom_ids:
            cur.execute("INSERT OR IGNORE INTO community_atoms(community_id, atom_id) VALUES (?,?)", (c.id, aid))
