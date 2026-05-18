from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Optional

from ..config import Config
from ..expand import Neighborhood, RawEdge
from ..ir import Paper
from . import IMPLEMENTATION_CRITICAL, ROLES
from .heuristic import RolePrediction, classify_heuristic
from .llm import classify_llm

LLM_THRESHOLD = 0.55


@dataclass
class ClassifiedEdge:
    edge: RawEdge
    roles: list[RolePrediction]
    classifier: str  # "heuristic" | "llm"


def _top_confidence(preds: list[RolePrediction]) -> float:
    return preds[0].confidence if preds else 0.0


async def classify_edges(cfg: Config, target: Paper, neighborhood: Neighborhood) -> list[ClassifiedEdge]:
    out: list[ClassifiedEdge] = []
    llm_budget = cfg.compile.classifier_llm_max_calls

    edges_sorted = sorted(neighborhood.edges, key=lambda e: 0 if e.section_type == "method" else 1)

    for edge in edges_sorted:
        neighbor = neighborhood.papers.get(edge.to_paper_id)
        heur = classify_heuristic(edge, neighbor)
        top_conf = _top_confidence(heur)
        if top_conf < LLM_THRESHOLD and llm_budget > 0:
            llm_preds = classify_llm(cfg, edge, neighbor)
            if llm_preds:
                out.append(ClassifiedEdge(edge=edge, roles=llm_preds, classifier="llm"))
                llm_budget -= 1
                continue
        out.append(ClassifiedEdge(edge=edge, roles=heur, classifier="heuristic"))

    n_llm = sum(1 for e in out if e.classifier == "llm")
    print(f"classify: {len(out)} edges ({n_llm} via LLM)", file=sys.stderr)
    return out


def best_role(edge: ClassifiedEdge) -> tuple[str, float]:
    if not edge.roles:
        return ("related_work_only", 0.0)
    top = edge.roles[0]
    return (top.label, top.confidence)


def is_implementation_critical(edge: ClassifiedEdge) -> bool:
    return best_role(edge)[0] in IMPLEMENTATION_CRITICAL
