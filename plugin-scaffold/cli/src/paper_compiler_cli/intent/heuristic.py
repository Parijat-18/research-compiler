"""Heuristic citation-intent classifier.

Same architecture as ``classify/heuristic.py`` — section priors plus
keyword hints. Cheap (no LLM call, no model load) and recovers ~70% of
intents in the JEPA audit corpus correctly. Edges where the heuristic
confidence is below ``LLM_INTENT_THRESHOLD`` are routed to the LLM
fallback in ``intent/llm.py``.

Hints chosen from a manual scan of the JEPA neighborhood's edges:

- ``contrasts`` triggers on negation tokens near a citation. The audit
  noted that "negative result" / "fails / cannot / unlike" patterns are
  the only signal we have without LLM judgment.
- ``method`` triggers on "we use", "follow", "based on", "implement" plus
  artifact proximity (a citation near an equation or algorithm in the
  method section is overwhelmingly methodological).
- ``extends`` triggers on "we extend", "we generalize", "building on".
- ``result`` triggers on "achieves", "report", numeric values nearby.
- ``background`` is the related_work fallback.
- ``mention`` is the abstract/conclusion/passing-reference fallback.
"""

from __future__ import annotations

import re
from typing import Optional

from ..expand import NeighborPaper, RawEdge
from . import INTENT_LABELS, IntentResult

CONTRAST_HINTS = (
    "unlike", "contrary", "however", "in contrast", "fails to",
    "does not", "cannot", "no longer", "refute", "we disagree",
    "differs from", "outperform", "worse than", "instead of",
)
NEGATION_PROXIMITY = re.compile(
    r"\b(?:not|no|without|fail(?:s|ed)?|cannot|refute[ds]?|unlike|contrary)\b",
    re.IGNORECASE,
)

METHOD_HINTS = (
    "we use", "we adopt", "we follow", "we apply", "we employ",
    "based on", "follows", "following", "implement", "leverag",
    "build on", "built on", "borrow", "borrowed", "adopt",
    "as in", "akin to", "similar to",
)
EXTENDS_HINTS = (
    "we extend", "extend the", "we generalize", "we build on",
    "improves upon", "improve upon", "we improve",
    "enhance", "we modify", "our extension",
)
RESULT_HINTS = (
    "achieve", "achieves", "achieved", "report", "reports",
    "reported", "outperform", "outperforms", "outperformed",
    "accuracy", "score", "result", "f1", "rouge", "bleu",
)
BACKGROUND_HINTS = (
    "prior work", "previous work", "earlier work", "introduced",
    "originally proposed", "first proposed", "popularized",
    "seminal", "classical",
)

# Numeric proximity → result intent (tables, accuracy numbers, etc.)
_NUM_RE = re.compile(r"\b\d+\.\d+\b")


def _hits(text: str, hints: tuple[str, ...]) -> int:
    return sum(1 for h in hints if h in text)


def _confidence_from_total(score: float, total: float) -> float:
    if total <= 0:
        return 0.0
    return min(0.95, score / total)


def classify_intent_heuristic(
    edge: RawEdge,
    neighbor: Optional[NeighborPaper] = None,
) -> IntentResult:
    """Score each intent label using section priors + keyword hints.

    Returns the top intent plus the full ranked list so the DB can record
    multi-intent labels (a method+result citation, for example).
    """
    txt = (edge.context or "").lower()
    section = edge.section_type

    scores: dict[str, float] = {label: 0.0 for label in INTENT_LABELS}

    # ---- section priors -------------------------------------------------- #
    # Method sections heavily bias toward method/extends; experiments
    # sections toward result; related_work toward background; intro toward
    # mention; everything else stays neutral.
    if section == "method":
        scores["method"] += 0.5
        scores["extends"] += 0.15
    elif section == "experiments":
        scores["result"] += 0.45
        scores["method"] += 0.1
    elif section == "results":
        scores["result"] += 0.45
    elif section == "related_work":
        scores["background"] += 0.5
        scores["mention"] += 0.15
    elif section == "introduction":
        scores["background"] += 0.25
        scores["mention"] += 0.2
    elif section in {"abstract", "conclusion"}:
        scores["mention"] += 0.3
    elif section == "":
        # Phantom edge (no paragraph match) — bib-only reference.
        scores["mention"] += 0.4

    # ---- keyword hints --------------------------------------------------- #
    scores["method"] += 0.18 * _hits(txt, METHOD_HINTS)
    scores["extends"] += 0.25 * _hits(txt, EXTENDS_HINTS)
    scores["result"] += 0.18 * _hits(txt, RESULT_HINTS)
    scores["background"] += 0.18 * _hits(txt, BACKGROUND_HINTS)
    scores["contrasts"] += 0.3 * _hits(txt, CONTRAST_HINTS)

    # Negation token NEAR the citation marker → contrasts boost. This
    # catches "unlike [3] we ..." and "[4] fails to ...".
    if NEGATION_PROXIMITY.search(txt[:300]):
        scores["contrasts"] += 0.25

    # ---- artifact proximity --------------------------------------------- #
    if edge.nearby_equation_ids or edge.nearby_algorithm_ids:
        scores["method"] += 0.25
    if edge.nearby_table_ids:
        scores["result"] += 0.2
    # Numeric values in context → result intent.
    if _NUM_RE.search(txt):
        scores["result"] += 0.1

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    top = [(label, s) for label, s in ranked if s > 0]
    if not top:
        return IntentResult(
            best_label="mention",
            best_confidence=0.2,
            intents=[{"label": "mention", "confidence": 0.2}],
            source="heuristic",
        )

    total = sum(s for _, s in top) or 1.0
    intents = [
        {"label": label, "confidence": round(_confidence_from_total(s, total), 3)}
        for label, s in top[:3]
    ]
    return IntentResult(
        best_label=intents[0]["label"],
        best_confidence=intents[0]["confidence"],
        intents=intents,
        source="heuristic",
    )
