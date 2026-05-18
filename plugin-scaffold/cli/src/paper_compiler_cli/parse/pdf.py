from __future__ import annotations

import re
from pathlib import Path

from ..ir import Citation, Equation, Paper, Paragraph, Reference, Section, classify_section_title

_HEADING_RE = re.compile(r"^(#{1,4})\s+(.+?)\s*$")
_EQ_RE = re.compile(r"\$\$(.+?)\$\$", re.DOTALL)
_INLINE_CITE_RE = re.compile(r"\[(\d{1,3}(?:\s*,\s*\d{1,3})*)\]")


def _markdown_from_marker(pdf_path: Path) -> str:
    try:
        from marker.converters.pdf import PdfConverter
        from marker.models import create_model_dict
        from marker.output import text_from_rendered
    except ImportError as e:  # noqa: BLE001
        raise ImportError("marker-pdf not installed; pip install paper-compiler-cli[pdf]") from e

    converter = PdfConverter(artifact_dict=create_model_dict())
    rendered = converter(str(pdf_path))
    text, _, _ = text_from_rendered(rendered)
    return text


def parse_pdf(paper: Paper, pdf_path: Path) -> Paper:
    md = _markdown_from_marker(pdf_path)
    lines = md.splitlines()
    sections: list[Section] = []
    equations: list[Equation] = []
    current: Section | None = None
    sec_n = 0
    para_n = 0
    para_buf: list[str] = []
    eq_n = 0
    references: list[Reference] = []
    ref_seen: dict[str, str] = {}

    def flush() -> None:
        nonlocal para_n
        if not para_buf or current is None:
            para_buf.clear()
            return
        text = re.sub(r"\s+", " ", " ".join(para_buf)).strip()
        if not text:
            para_buf.clear()
            return
        para_n += 1
        pid = f"{current.id}-p{para_n}"
        citations: list[Citation] = []
        for m in _INLINE_CITE_RE.finditer(text):
            for n in re.split(r",\s*", m.group(1)):
                key = f"ref-{n}"
                marker = f"[{n}]"
                if key not in ref_seen:
                    ref_seen[key] = key
                    references.append(Reference(ref_id=key, marker=marker, raw=marker))
                citations.append(Citation(marker=marker, ref_id=key, context_window=text[:400]))
        current.paragraphs.append(Paragraph(id=pid, text=text, citations=citations))
        para_buf.clear()

    in_refs = False
    for line in lines:
        h = _HEADING_RE.match(line)
        if h:
            flush()
            title = h.group(2).strip()
            sec_n += 1
            para_n = 0
            current = Section(
                id=f"sec-{sec_n}",
                title=title,
                level=len(h.group(1)),
                section_type=classify_section_title(title),
            )
            sections.append(current)
            in_refs = "reference" in title.lower() or "bibliograph" in title.lower()
            continue
        if not line.strip():
            flush()
            continue
        if in_refs:
            txt = line.strip()
            if txt:
                rid = f"ref-{len(references) + 1}"
                references.append(Reference(ref_id=rid, marker=f"[{len(references) + 1}]", raw=txt))
            continue
        for m in _EQ_RE.finditer(line):
            eq_n += 1
            equations.append(
                Equation(
                    id=f"eq-{eq_n}",
                    latex=m.group(1).strip(),
                    section_id=current.id if current else None,
                )
            )
        para_buf.append(line)
    flush()

    paper.sections = sections
    paper.equations = equations
    paper.references = references
    return paper
