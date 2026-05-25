from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Optional

from ..config import Config
from ..expand import Neighborhood, RawEdge
from ..intent import IntentResult, intent_weight
from ..intent.heuristic import classify_intent_heuristic
from ..intent.llm import classify_intent_llm
from ..ir import Paper
from . import IMPLEMENTATION_CRITICAL, ROLES, role_weight
from .heuristic import RolePrediction, classify_heuristic
from .llm import classify_llm

# Roles below this threshold trigger the LLM residual classifier.
LLM_THRESHOLD = 0.55
# Intents below this threshold trigger the LLM residual intent classifier.
LLM_INTENT_THRESHOLD = 0.45


@dataclass
class ClassifiedEdge:
    edge: RawEdge
    roles: list[RolePrediction]
    classifier: str  # "heuristic" | "llm"
    # Phase 4 fields. ``provenance_rule`` records *how* the edge was discovered
    # (inline cite vs bib resolve), independent of *who* classified it. The
    # ``classifier`` field above already records the latter.
    provenance_rule: Optional[str] = None
    citation_intent: Optional[str] = None
    intent_confidence: Optional[float] = None
    intents: list[dict] = field(default_factory=list)
    intent_source: Optional[str] = None
    weight: Optional[float] = None


def _top_confidence(preds: list[RolePrediction]) -> float:
    return preds[0].confidence if preds else 0.0


def _provenance_for(edge: RawEdge) -> str:
    """Where did this edge come from?

    - inline_cite_match: paragraph contained an inline citation marker that
      resolved against the bibliography.
    - bib_resolve: phantom edge synthesized in expand.py from a resolved
      reference that wasn't cited at the paragraph level (S2 references
      endpoint, or bib entries with no body cite).
    """
    if edge.paragraph_id and edge.section_id:
        return "inline_cite_match"
    return "bib_resolve"


def _compute_weight(
    best_conf: float,
    best_role_label: str,
    intent_label: Optional[str],
) -> float:
    """Final per-edge weight = confidence × role_weight × intent_weight.

    Bounded to [0, 2.0] so a single very-high-intent edge can't dominate
    traversal. Floor at 0 (never negative).
    """
    w = float(best_conf) * role_weight(best_role_label) * intent_weight(intent_label)
    return round(max(0.0, min(2.0, w)), 4)


async def classify_edges(cfg: Config, target: Paper, neighborhood: Neighborhood) -> list[ClassifiedEdge]:
    out: list[ClassifiedEdge] = []
    role_llm_budget = cfg.compile.classifier_llm_max_calls
    intent_llm_budget = cfg.compile.classifier_llm_max_calls

    edges_sorted = sorted(neighborhood.edges, key=lambda e: 0 if e.section_type == "method" else 1)

    for edge in edges_sorted:
        neighbor = neighborhood.papers.get(edge.to_paper_id)

        # ----- role classification (existing heuristic → LLM fallback) -----
        heur = classify_heuristic(edge, neighbor)
        top_conf = _top_confidence(heur)
        roles = heur
        classifier = "heuristic"
        provenance = _provenance_for(edge)
        if top_conf < LLM_THRESHOLD and role_llm_budget > 0:
            llm_preds = classify_llm(cfg, edge, neighbor)
            if llm_preds:
                roles = llm_preds
                classifier = "llm"
                provenance = "llm_judgment"
                role_llm_budget -= 1

        best_label = roles[0].label if roles else "related_work_only"
        best_conf = roles[0].confidence if roles else 0.0

        # ----- intent classification (new — heuristic → LLM fallback) -----
        intent = classify_intent_heuristic(edge, neighbor)
        if intent.best_confidence < LLM_INTENT_THRESHOLD and intent_llm_budget > 0:
            llm_intent = classify_intent_llm(cfg, edge, neighbor)
            if llm_intent is not None:
                intent = llm_intent
                intent_llm_budget -= 1

        weight = _compute_weight(best_conf, best_label, intent.best_label)

        out.append(
            ClassifiedEdge(
                edge=edge,
                roles=roles,
                classifier=classifier,
                provenance_rule=provenance,
                citation_intent=intent.best_label,
                intent_confidence=intent.best_confidence,
                intents=intent.intents,
                intent_source=intent.source,
                weight=weight,
            )
        )

    n_llm_roles = sum(1 for e in out if e.classifier == "llm")
    n_llm_intents = sum(1 for e in out if e.intent_source == "llm")
    n_contradicts = sum(1 for e in out if e.roles and e.roles[0].label == "contradicts")
    print(
        f"classify: {len(out)} edges "
        f"(role-llm={n_llm_roles}, intent-llm={n_llm_intents}, contradicts={n_contradicts})",
        file=sys.stderr,
    )
    return out


def best_role(edge: ClassifiedEdge) -> tuple[str, float]:
    if not edge.roles:
        return ("related_work_only", 0.0)
    top = edge.roles[0]
    return (top.label, top.confidence)


def is_implementation_critical(edge: ClassifiedEdge) -> bool:
    return best_role(edge)[0] in IMPLEMENTATION_CRITICAL
