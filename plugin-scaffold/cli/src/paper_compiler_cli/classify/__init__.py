ROLES = (
    # v1.0: parallel to ATOM_CATEGORIES — every dependency role maps to a
    # category. Domain-neutral so the same role taxonomy serves ML papers,
    # physics simulations, chemistry methods, and biology protocols.
    "method_dependency",
    "objective_dependency",
    "data_dependency",
    "preprocessing_dependency",
    "evaluation_dependency",
    "baseline_dependency",
    "procedure_dependency",
    "theory_dependency",
    # Phase 4: a citation that disagrees with / refutes the cited paper.
    # Detected via negation-token proximity heuristic + LLM residual.
    "contradicts",
    "ablation_reference",
    "engineering_reference",
    "related_work_only",
)

IMPLEMENTATION_CRITICAL = ROLES[:8]

# Per-role contribution to the final edge weight. Implementation-critical
# roles are full-strength; ablation/engineering references are half; passing
# related-work mentions are heavily suppressed. ``contradicts`` keeps full
# weight because a refutation IS signal — just signal pointing the other
# direction for retrieval reranking.
ROLE_WEIGHT: dict[str, float] = {
    "method_dependency": 1.0,
    "objective_dependency": 1.0,
    "data_dependency": 1.0,
    "preprocessing_dependency": 1.0,
    "evaluation_dependency": 1.0,
    "baseline_dependency": 1.0,
    "procedure_dependency": 1.0,
    "theory_dependency": 0.8,
    "contradicts": 1.0,
    "ablation_reference": 0.5,
    "engineering_reference": 0.5,
    "related_work_only": 0.2,
}

# Public mapping from role to atom category. Used by atoms/extract.py to
# attribute "this citation in the experiments section maps to a baseline
# atom" without each module hardcoding its own translation.
ROLE_TO_CATEGORY: dict[str, str] = {
    "method_dependency": "method",
    "objective_dependency": "objective",
    "data_dependency": "data",
    "preprocessing_dependency": "preprocessing",
    "evaluation_dependency": "evaluation",
    "baseline_dependency": "baseline",
    "procedure_dependency": "procedure",
    "theory_dependency": "theory",
}


def role_weight(role: str | None) -> float:
    if not role:
        return 1.0
    return ROLE_WEIGHT.get(role, 1.0)
