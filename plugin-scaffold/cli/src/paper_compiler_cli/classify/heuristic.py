from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from ..expand import NeighborPaper, RawEdge
from ..ir import SectionType
from . import ROLES

ARCH_HINTS = ("architecture", "encoder", "decoder", "transformer", "attention", "backbone", "block", "module", "layer", "network")
LOSS_HINTS = ("loss", "objective", "log-likelihood", "regulariz", "kl", "cross-entropy", "contrastive", "reward", "penalty")
DATASET_HINTS = ("dataset", "corpus", "imagenet", "coco", "wikitext", "c4", "the pile", "common crawl", "benchmark", "split")
PREPROC_HINTS = ("preprocess", "tokeniz", "augment", "normaliz", "patchif", "embed", "filter")
EVAL_HINTS = ("evaluat", "metric", "benchmark", "score", "rouge", "bleu", "accuracy", "f1")
BASELINE_HINTS = ("baseline", "we compare", "outperform", "against", "previous best")
OPT_HINTS = ("adam", "sgd", "warmup", "schedule", "learning rate", "lr", "mixed precision", "ema", "weight decay")
THEORY_HINTS = ("theorem", "lemma", "proof", "assumption", "convergence", "bound")
ABLATION_HINTS = ("ablation", "we ablate", "removing")
ENG_HINTS = ("pytorch", "tensorflow", "jax", "cuda", "flashattention", "deepspeed", "library", "framework", "implement")


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
        for r in ("architecture_dependency", "loss_function_dependency", "preprocessing_dependency"):
            scores[r] += 0.4
    elif section == "experiments":
        for r in ("dataset_dependency", "evaluation_protocol_dependency", "baseline_dependency"):
            scores[r] += 0.4
    elif section == "related_work":
        scores["related_work_only"] += 0.6
    elif section == "introduction":
        scores["related_work_only"] += 0.3

    # text hints
    scores["architecture_dependency"] += 0.15 * _hits(txt, ARCH_HINTS)
    scores["loss_function_dependency"] += 0.2 * _hits(txt, LOSS_HINTS)
    scores["dataset_dependency"] += 0.18 * _hits(txt, DATASET_HINTS)
    scores["preprocessing_dependency"] += 0.18 * _hits(txt, PREPROC_HINTS)
    scores["evaluation_protocol_dependency"] += 0.18 * _hits(txt, EVAL_HINTS)
    scores["baseline_dependency"] += 0.2 * _hits(txt, BASELINE_HINTS)
    scores["optimizer_or_training_trick"] += 0.2 * _hits(txt, OPT_HINTS)
    scores["theoretical_assumption"] += 0.2 * _hits(txt, THEORY_HINTS)
    scores["ablation_reference"] += 0.3 * _hits(txt, ABLATION_HINTS)
    scores["engineering_reference"] += 0.18 * _hits(txt, ENG_HINTS)

    # artifact proximity boosts
    if edge.nearby_equation_ids:
        scores["loss_function_dependency"] += 0.25
        scores["architecture_dependency"] += 0.15
        scores["theoretical_assumption"] += 0.15
    if edge.nearby_algorithm_ids:
        scores["architecture_dependency"] += 0.2
        scores["optimizer_or_training_trick"] += 0.2
    if edge.nearby_table_ids:
        scores["baseline_dependency"] += 0.2
        scores["evaluation_protocol_dependency"] += 0.2

    # title prior from cited paper
    if neighbor and neighbor.record:
        title = (neighbor.record.get("title") or "").lower()
        if any(w in title for w in ("dataset", "corpus")):
            scores["dataset_dependency"] += 0.3
        if any(w in title for w in ("optimizer", "adam", "training")):
            scores["optimizer_or_training_trick"] += 0.2
        if any(w in title for w in ("transformer", "attention", "encoder")):
            scores["architecture_dependency"] += 0.2
        types = neighbor.record.get("publicationTypes") or []
        if "Dataset" in types:
            scores["dataset_dependency"] += 0.4

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
