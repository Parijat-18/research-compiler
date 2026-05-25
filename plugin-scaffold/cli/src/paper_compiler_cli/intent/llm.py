"""LLM-based citation-intent classifier (fallback for low-confidence heuristics).

Used only when ``classify_intent_heuristic`` returns a confidence below
``LLM_INTENT_THRESHOLD``. The LLM call mirrors ``classify/llm.py``: a
SYSTEM prompt locking the output schema, a USER message carrying the edge
context. Re-uses the existing ``llm.call_llm`` backend selection
(claude_cli > Anthropic SDK > none).

The classifier budget is shared with the role classifier via
``cfg.compile.classifier_llm_max_calls`` — same total ceiling per compile.
"""

from __future__ import annotations

from typing import Optional

from ..config import Config
from ..expand import NeighborPaper, RawEdge
from ..llm import call_llm, parse_json_object
from . import INTENT_LABELS, IntentResult

_SYSTEM = (
    "You classify a citation in a research paper into one or more "
    "intent labels. The paper may be from any scientific or engineering "
    "field — ML, physics, chemistry, biology, economics, climate, etc.\n"
    'Return ONLY JSON: {"intents": [{"label": "<label>", "confidence": <0..1>}], '
    '"rationale": "<≤25 words>"}.\n'
    "Allowed labels: " + ", ".join(INTENT_LABELS) + ".\n"
    "Definitions (domain-neutral):\n"
    "- mention: passing reference, no methodological dependence.\n"
    "- background: situating the paper in prior literature.\n"
    "- result: citing the cited paper's experimental/empirical results.\n"
    "- method: using a method/scheme/protocol/dataset/measurement procedure from the cited paper.\n"
    "- extends: directly extending or generalizing the cited work.\n"
    "- contrasts: disagrees with, refutes, or fails to reproduce.\n"
    "Multi-label is allowed (e.g. method+result for a baseline). Confidence is "
    "the model's own estimate; do not invent precision."
)


def _build_user(edge: RawEdge, neighbor: Optional[NeighborPaper]) -> str:
    cited_title = ""
    if neighbor and neighbor.record:
        cited_title = neighbor.record.get("title") or ""
    return (
        f"section_type: {edge.section_type}\n"
        f"cited_title: {cited_title}\n"
        f"nearby_equations: {edge.nearby_equation_ids}\n"
        f"nearby_tables: {edge.nearby_table_ids}\n"
        f"context:\n{(edge.context or '')[:600]}"
    )


def classify_intent_llm(
    cfg: Config,
    edge: RawEdge,
    neighbor: Optional[NeighborPaper],
) -> Optional[IntentResult]:
    result = call_llm(cfg, _SYSTEM, _build_user(edge, neighbor), max_tokens=250)
    if result is None:
        return None
    data = parse_json_object(result.text)
    if not data:
        return None
    intents: list[dict] = []
    for r in data.get("intents") or []:
        label = r.get("label")
        if label in INTENT_LABELS:
            conf = max(0.0, min(1.0, float(r.get("confidence", 0.5))))
            intents.append({"label": label, "confidence": round(conf, 3)})
    if not intents:
        return None
    intents.sort(key=lambda x: x["confidence"], reverse=True)
    return IntentResult(
        best_label=intents[0]["label"],
        best_confidence=intents[0]["confidence"],
        intents=intents,
        source="llm",
    )
