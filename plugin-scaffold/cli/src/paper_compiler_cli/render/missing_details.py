from __future__ import annotations

from pathlib import Path
from typing import Any


def write_missing_details(path: Path, graph: dict[str, Any]) -> None:
    items = graph.get("missing_details", [])
    lines = ["# Open implementation questions\n"]
    if not items:
        lines.append("_No unresolved details detected by the compiler. Verify manually before implementation._\n")
    else:
        for i, item in enumerate(items, 1):
            lines.append(f"## {i}. {item.get('question', '')} (`{item.get('id', '')}`)")
            lines.append(f"- **Category:** {item.get('category', '')}")
            if item.get("options"):
                lines.append(f"- **Options:** {', '.join(item['options'])}")
            if item.get("suggested_default"):
                lines.append(f"- **Suggested default:** {item['suggested_default']}")
            if item.get("rationale"):
                lines.append(f"- **Rationale:** {item['rationale']}")
            lines.append("")
    path.write_text("\n".join(lines))
