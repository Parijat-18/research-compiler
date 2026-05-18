from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class Condition:
    name: Literal["A", "B", "C"]
    install_plugin: bool
    enable_mcp_tools: bool
    enable_use_skill: bool
    description: str


CONDITIONS: dict[str, Condition] = {
    "A": Condition(
        name="A",
        install_plugin=False,
        enable_mcp_tools=False,
        enable_use_skill=False,
        description="Baseline: target paper PDF (or arXiv link) only. No plugin installed.",
    ),
    "B": Condition(
        name="B",
        install_plugin=True,
        enable_mcp_tools=False,
        enable_use_skill=True,
        description="Brief only: research.md + missing-details.md, MCP tools disabled.",
    ),
    "C": Condition(
        name="C",
        install_plugin=True,
        enable_mcp_tools=True,
        enable_use_skill=True,
        description="Full plugin: research.md + missing-details.md + MCP tools.",
    ),
}

# Standardized implementation prompt — identical across conditions (eval §4).
IMPLEMENTATION_PROMPT = (
    "Implement this paper end-to-end. Aim for a runnable repo that matches "
    "the paper's method as closely as possible. Where the paper is ambiguous, "
    "make a reasoned choice and document it. Don't run experiments — focus on "
    "faithful implementation."
)

SESSION_BUDGET = {
    "wall_minutes": 60,
    "max_tool_calls": 200,
}
