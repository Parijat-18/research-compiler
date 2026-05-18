from __future__ import annotations

import math
from typing import Iterable

from .atoms import Atom
from .classify.edge import ClassifiedEdge, best_role
from .expand import Neighborhood
from .ir import Paper


def _scholarly(rec: dict | None) -> float:
    if not rec:
        return 0.0
    cc = rec.get("citationCount") or 0
    icc = rec.get("influentialCitationCount") or 0
    year = rec.get("year") or 2000
    recency = max(0.0, 1.0 - (2026 - year) / 30.0)
    return 0.3 * math.log1p(cc) + 0.4 * math.log1p(icc) + 0.3 * recency


def _implementation(pid: str, edges: list[ClassifiedEdge], atoms: list[Atom]) -> float:
    base = 0.0
    for ce in edges:
        if ce.edge.to_paper_id != pid:
            continue
        _, conf = best_role(ce)
        base += conf
        if ce.edge.nearby_equation_ids:
            base += 0.3
        if ce.edge.nearby_algorithm_ids:
            base += 0.2
        if ce.edge.section_type == "method":
            base += 0.3
    defined = sum(1 for a in atoms if a.defined_by_paper_id == pid)
    return base + 0.5 * defined


def score_papers(
    target: Paper,
    neighborhood: Neighborhood,
    edges: list[ClassifiedEdge],
    atoms: list[Atom],
) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for pid, np in neighborhood.papers.items():
        sch = _scholarly(np.record)
        imp = _implementation(pid, edges, atoms)
        out[pid] = {
            "scholarly_influence": round(sch, 4),
            "implementation_influence": round(imp, 4),
            "rank": round(0.7 * imp + 0.3 * sch, 4),
        }
    out[target.paper_id] = {
        "scholarly_influence": 0.0,
        "implementation_influence": float(len(atoms)),
        "rank": 1.0,
    }
    return out


_CATEGORY_ORDER = ("dataset", "preprocessing", "architecture", "loss", "optimizer", "training_trick", "hyperparameter", "evaluation", "baseline")


def topological_order(atoms: list[Atom]) -> list[dict]:
    by_id = {a.id: a for a in atoms}
    visited: set[str] = set()
    order: list[Atom] = []

    def visit(a: Atom) -> None:
        if a.id in visited:
            return
        visited.add(a.id)
        for d in a.dependencies:
            if d in by_id:
                visit(by_id[d])
        order.append(a)

    cat_rank = {c: i for i, c in enumerate(_CATEGORY_ORDER)}
    for a in sorted(atoms, key=lambda x: (cat_rank.get(x.category, 99), -x.priority)):
        visit(a)
    return [{"atom_id": a.id, "rationale": f"category={a.category}, priority={a.priority:.2f}"} for a in order]
