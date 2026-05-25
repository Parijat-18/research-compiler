from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from ..domain_patterns import (
    ABLATION_HINTS,
    ARCH_HINTS,
    BASELINE_HINTS,
    CONTRADICTS_HINTS,
    DATASET_HINTS,
    DOMAIN_TITLE_HINTS,
    ENG_HINTS,
    EVAL_HINTS,
    LOSS_HINTS,
    OPT_HINTS,
    PREPROC_HINTS,
    THEORY_HINTS,
)
from ..expand import NeighborPaper, RawEdge
from ..ir import SectionType
from . import ROLES

# Phase 4: a citation surrounded by negation/refutation tokens is a
# candidate "contradicts" edge. The proximity (≤ ~50 chars) matters more
# than the count of hits; we tally hits and also boost from explicit
# negation tokens in the first 300 chars (where inline citations live).
# This regex is domain-neutral — every field uses negation grammar.
_NEG_PROXIMITY_RE = re.compile(
    r"\b(?:not|no|without|fail(?:s|ed)?|cannot|refute[ds]?|unlike|contrary|differ(?:s|ed)?)\b",
    re.IGNORECASE,
)


@dataclass
class RolePrediction:
    label: str
    confidence: float


def _hits(text: str, hints: tuple[str, ...]) -> int:
    return sum(1 for h in hints if h in text)


def classify_heuristic(edge: RawEdge, neighbor: Optional[NeighborPaper] = None) -> list[RolePrediction]:
    txt = edge.context.lower()
    section = edge.section_type
    scores: dict[str, float] = {r: 0.0 for r in ROLES}

    # section priors
    if section == "method":
        for r in ("method_dependency", "objective_dependency", "preprocessing_dependency"):
            scores[r] += 0.4
    elif section == "experiments":
        for r in ("data_dependency", "evaluation_dependency", "baseline_dependency"):
            scores[r] += 0.4
    elif section == "related_work":
        scores["related_work_only"] += 0.6
    elif section == "introduction":
        scores["related_work_only"] += 0.3

    # text hints. The keyword sets are deliberately broad-STEM (see
    # domain_patterns.py) so a physics simulation paper or a chemistry
    # methods paper isn't disadvantaged relative to ML. Users can swap
    # in a domain-specific pack via cfg.domain.preset.
    scores["method_dependency"] += 0.15 * _hits(txt, ARCH_HINTS)
    scores["objective_dependency"] += 0.2 * _hits(txt, LOSS_HINTS)
    scores["data_dependency"] += 0.18 * _hits(txt, DATASET_HINTS)
    scores["preprocessing_dependency"] += 0.18 * _hits(txt, PREPROC_HINTS)
    scores["evaluation_dependency"] += 0.18 * _hits(txt, EVAL_HINTS)
    scores["baseline_dependency"] += 0.2 * _hits(txt, BASELINE_HINTS)
    scores["procedure_dependency"] += 0.2 * _hits(txt, OPT_HINTS)
    scores["theory_dependency"] += 0.2 * _hits(txt, THEORY_HINTS)
    scores["ablation_reference"] += 0.3 * _hits(txt, ABLATION_HINTS)
    scores["engineering_reference"] += 0.18 * _hits(txt, ENG_HINTS)
    # Phase 4: contradicts. Hint count + a hard boost when a negation
    # token appears in the citation's neighborhood (first 300 chars of
    # context). The boost dominates because phrases like "unlike [3]" are
    # very strong contradiction signals even at low hint counts.
    scores["contradicts"] += 0.25 * _hits(txt, CONTRADICTS_HINTS)
    if _NEG_PROXIMITY_RE.search(txt[:300]):
        scores["contradicts"] += 0.35

    # artifact proximity boosts (domain-neutral: every field has equations,
    # algorithms/pseudocode, and tables)
    if edge.nearby_equation_ids:
        scores["objective_dependency"] += 0.25
        scores["method_dependency"] += 0.15
        scores["theory_dependency"] += 0.15
    if edge.nearby_algorithm_ids:
        scores["method_dependency"] += 0.2
        scores["procedure_dependency"] += 0.2
    if edge.nearby_table_ids:
        scores["baseline_dependency"] += 0.2
        scores["evaluation_dependency"] += 0.2

    # title prior from cited paper. We keep this generic by relying on
    # the domain pack (DOMAIN_TITLE_HINTS) rather than hardcoding ML
    # vocabulary. Each entry says: "if any of these words appear in the
    # cited paper's title, boost this role".
    if neighbor and neighbor.record:
        title = (neighbor.record.get("title") or "").lower()
        for role, hints in DOMAIN_TITLE_HINTS.items():
            if any(w in title for w in hints):
                scores[role] += 0.2
        types = neighbor.record.get("publicationTypes") or []
        if "Dataset" in types:
            scores["data_dependency"] += 0.4

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    top = [(r, s) for r, s in ranked if s > 0]
    if not top:
        return [RolePrediction("related_work_only", 0.2)]
    # confidence = top normalized score, capped at 0.95
    total = sum(s for _, s in top) or 1.0
    out: list[RolePrediction] = []
    for r, s in top[:3]:
        out.append(RolePrediction(label=r, confidence=min(0.95, s / total)))
    return out
