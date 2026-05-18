from __future__ import annotations

from typing import Optional

from ..config import Config
from ..expand import NeighborPaper, RawEdge
from ..llm import call_llm, parse_json_object
from . import ROLES
from .heuristic import RolePrediction

_SYSTEM = (
    "You classify a citation edge from a research paper into implementation roles.\n"
    'Return only JSON: {"roles": [{"label": "<role>", "confidence": <0..1>}], "rationale": "<≤30 words>"}.\n'
    "Allowed labels: " + ", ".join(ROLES) + "."
)


def _build_user(edge: RawEdge, neighbor: Optional[NeighborPaper]) -> str:
    cited_title = ""
    if neighbor and neighbor.record:
        cited_title = neighbor.record.get("title") or ""
    return (
        f"section_type: {edge.section_type}\n"
        f"cited_title: {cited_title}\n"
        f"nearby_equations: {edge.nearby_equation_ids}\n"
        f"nearby_algorithms: {edge.nearby_algorithm_ids}\n"
        f"nearby_tables: {edge.nearby_table_ids}\n"
        f"context:\n{edge.context}"
    )


def classify_llm(cfg: Config, edge: RawEdge, neighbor: Optional[NeighborPaper]) -> Optional[list[RolePrediction]]:
    result = call_llm(cfg, _SYSTEM, _build_user(edge, neighbor), max_tokens=300)
    if result is None:
        return None
    data = parse_json_object(result.text)
    if not data:
        return None
    out: list[RolePrediction] = []
    for r in data.get("roles") or []:
        label = r.get("label")
        if label in ROLES:
            conf = float(r.get("confidence", 0.5))
            out.append(RolePrediction(label=label, confidence=max(0.0, min(1.0, conf))))
    return out or None
