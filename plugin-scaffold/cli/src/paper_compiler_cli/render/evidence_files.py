from __future__ import annotations

from pathlib import Path

from ..atoms import Atom, EvidenceSpan


def write_evidence_files(evidence_dir: Path, atoms: list[Atom], evidence: list[EvidenceSpan]) -> None:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    ev_by_id = {e.id: e for e in evidence}
    for atom in atoms:
        path = evidence_dir / f"{atom.id}.md"
        lines = [
            f"# Evidence for `{atom.id}` — {atom.name}",
            "",
            f"- **Atom UID:** `{atom.uid}` (stable across rebuilds)",
            f"- **Display ID:** `{atom.id}` (sequential, may change)",
            f"- **Category:** {atom.category}",
            f"- **Defined by paper:** `{atom.defined_by_paper_id}`",
            f"- **Used by:** {', '.join(atom.used_by_paper_ids)}",
            f"- **Priority:** {atom.priority:.2f}",
            "",
            "## Description",
            atom.description or "_(none)_",
            "",
            "## Verbatim evidence spans",
            "",
        ]
        for eid in atom.evidence_span_ids:
            ev = ev_by_id.get(eid)
            if not ev:
                continue
            loc_bits = [f"section `{ev.section_id}` ({ev.section_type})"]
            if ev.paragraph_id:
                loc_bits.append(f"paragraph `{ev.paragraph_id}`")
            if ev.char_start is not None and ev.char_end is not None:
                loc_bits.append(f"chars {ev.char_start}–{ev.char_end}")
            lines.append(f"### `{ev.id}` — paper `{ev.paper_id}` · " + " · ".join(loc_bits))
            lines.append("")
            lines.append("> " + ev.verbatim_text.replace("\n", "\n> "))
            lines.append("")
        path.write_text("\n".join(lines))
