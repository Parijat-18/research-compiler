"""PDF → IR parser.

Two backends:

- **docling** (default, v2.0): IBM's open-source structured PDF parser. Walks
  ``DoclingDocument.iterate_items()`` so we get headings, tables, equations,
  and figures as typed structures rather than recovering them via regex over
  markdown. Typical speed on M-series Mac: ~1.0–1.5 s/page (vs Marker's
  10–15 s/page on CPU).

- **marker** (legacy, deprecated v1.0): renders the PDF to markdown via
  ``marker-pdf`` and then walks the markdown with regex to recover headings
  and equations. Kept behind ``parser.pdf_backend = "marker"`` for one
  release so users can A/B against the previous artifact.

Backend selection is driven by ``cfg.parser.pdf_backend`` and threaded
through ``parse/__init__.py:parse_paper``. The TeX path is still preferred
when an arXiv source tarball is available — Docling is the fallback path for
non-TeX papers (the majority of non-arXiv venues).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable, Optional

from ..ir import Citation, Equation, Figure, Paper, Paragraph, Reference, Section, Table, classify_section_title

_HEADING_RE = re.compile(r"^(#{1,4})\s+(.+?)\s*$")
_EQ_RE = re.compile(r"\$\$(.+?)\$\$", re.DOTALL)
# Match inline numeric citations like [3], [1,2], [10, 11].
_INLINE_CITE_RE = re.compile(r"\[(\d{1,3}(?:\s*,\s*\d{1,3})*)\]")
_REF_HEADING_RE = re.compile(r"^(references|bibliography|works cited|cited works)$", re.IGNORECASE)


# --------------------------------------------------------------------------- #
# Backend dispatcher
# --------------------------------------------------------------------------- #


def parse_pdf(paper: Paper, pdf_path: Path, *, backend: str = "docling") -> Paper:
    """Parse a PDF file into the Paper IR.

    Backend is selected by ``backend`` ("docling" or "marker"). When the
    selected backend is unavailable we raise ``ImportError`` and let the
    caller decide whether to skip the paper or retry with a different one.
    """
    if backend == "docling":
        return _parse_with_docling(paper, pdf_path)
    if backend == "marker":
        print(
            "warning: parser.pdf_backend='marker' is deprecated. "
            "Docling is ~10× faster and produces structured equations/tables. "
            "Switch via `parser.pdf_backend = \"docling\"`.",
            file=sys.stderr,
        )
        return _parse_with_marker(paper, pdf_path)
    raise ValueError(f"unknown pdf backend {backend!r}; expected 'docling' or 'marker'")


# --------------------------------------------------------------------------- #
# Docling (primary)
# --------------------------------------------------------------------------- #


def _docling_convert(pdf_path: Path):
    try:
        from docling.document_converter import DocumentConverter
    except ImportError as e:  # noqa: BLE001
        raise ImportError(
            "docling not installed; pip install paper-compiler-cli[pdf] (or install 'docling' directly)"
        ) from e
    return DocumentConverter().convert(str(pdf_path)).document


def _item_text(item) -> str:
    """Best-effort text accessor across Docling versions.

    Newer Docling exposes ``item.text``; older releases used ``item.orig`` or
    a ``.get_text()`` method. Try them in order so the parser doesn't break
    on a minor-version bump.
    """
    for attr in ("text", "orig"):
        val = getattr(item, attr, None)
        if isinstance(val, str) and val:
            return val
    getter = getattr(item, "get_text", None)
    if callable(getter):
        try:
            return getter() or ""
        except Exception:  # noqa: BLE001
            pass
    return ""


def _item_label(item) -> str:
    """Normalize Docling item labels (which may be Enum or str) to lowercase strings."""
    label = getattr(item, "label", None)
    if label is None:
        return ""
    name = getattr(label, "value", None) or getattr(label, "name", None) or str(label)
    return str(name).lower()


def _table_caption(table_item, doc) -> str:
    """Pull the caption text from a Docling TableItem.

    Tables hang their caption off ``captions: list[RefItem]`` in newer
    Docling; the older API was a ``caption`` string. Try both.
    """
    cap = getattr(table_item, "caption_text", None)
    if callable(cap):
        try:
            return str(cap(doc) or "")
        except Exception:  # noqa: BLE001
            pass
    caps = getattr(table_item, "captions", None) or []
    out: list[str] = []
    for ref in caps:
        # RefItem points to a TextItem elsewhere in the document
        resolve = getattr(ref, "resolve", None)
        if callable(resolve):
            try:
                target = resolve(doc)
                out.append(_item_text(target))
            except Exception:  # noqa: BLE001
                continue
        elif isinstance(ref, str):
            out.append(ref)
    if out:
        return " ".join(out).strip()
    fallback = getattr(table_item, "caption", None)
    return fallback if isinstance(fallback, str) else ""


def _table_rows(table_item) -> Optional[list[list[str]]]:
    """Extract table rows if Docling parsed them.

    Phase 6 will index tables as their own ``chunk_kind="table"`` entries;
    for Phase 2 we store rows on the IR if available, otherwise None.
    """
    data = getattr(table_item, "data", None)
    if data is None:
        return None
    rows = getattr(data, "grid", None)
    if not rows:
        return None
    try:
        return [[(cell.text if hasattr(cell, "text") else str(cell)) for cell in row] for row in rows]
    except Exception:  # noqa: BLE001
        return None


def _parse_with_docling(paper: Paper, pdf_path: Path) -> Paper:
    doc = _docling_convert(pdf_path)

    sections: list[Section] = []
    equations: list[Equation] = []
    tables: list[Table] = []
    figures: list[Figure] = []
    references: list[Reference] = []
    ref_index: dict[str, str] = {}

    current: Optional[Section] = None
    para_buf: list[str] = []
    sec_n = 0
    para_n = 0
    eq_n = 0
    tab_n = 0
    fig_n = 0
    in_references = False
    pending_caption_for: Optional[str] = None  # "table"/"figure" — apply next caption-labeled text

    def _open_section(title: str) -> None:
        nonlocal current, sec_n, para_n
        _flush_paragraph()
        sec_n += 1
        para_n = 0
        current = Section(
            id=f"sec-{sec_n}",
            title=title or f"Section {sec_n}",
            level=1,
            section_type=classify_section_title(title or ""),
        )
        sections.append(current)

    def _flush_paragraph() -> None:
        nonlocal para_n
        if not para_buf or current is None:
            para_buf.clear()
            return
        text = re.sub(r"\s+", " ", " ".join(para_buf)).strip()
        para_buf.clear()
        if not text:
            return
        para_n += 1
        pid = f"{current.id}-p{para_n}"
        citations = _extract_citations(text, references, ref_index)
        current.paragraphs.append(Paragraph(id=pid, text=text, citations=citations))

    def iter_items() -> Iterable:
        # Newer Docling: iterate_items() yields (item, level). Older: just items.
        it = doc.iterate_items() if hasattr(doc, "iterate_items") else iter(getattr(doc, "texts", []))
        for entry in it:
            if isinstance(entry, tuple):
                yield entry[0]
            else:
                yield entry

    for item in iter_items():
        label = _item_label(item)
        text = _item_text(item)

        # Page furniture pollutes retrieval and the reference list — skip
        # before the in_references branch so footers don't get mistaken for
        # bibliography entries.
        if label in {"page_header", "page_footer", "footnote"}:
            continue
        if label == "caption":
            # Captions for tables/figures are already attached via captions[];
            # ignore here to avoid duplicating them as body paragraphs.
            continue

        if label in {"title", "section_header"}:
            if _REF_HEADING_RE.match(text.strip()):
                _flush_paragraph()
                in_references = True
                current = None
                continue
            in_references = False
            _open_section(text.strip())
            continue

        if in_references:
            stripped = text.strip()
            if not stripped:
                continue
            rid = f"ref-{len(references) + 1}"
            references.append(
                Reference(ref_id=rid, marker=f"[{len(references) + 1}]", raw=stripped)
            )
            continue

        if label == "formula":
            eq_n += 1
            equations.append(
                Equation(
                    id=f"eq-{eq_n}",
                    latex=text.strip(),
                    section_id=current.id if current else None,
                )
            )
            continue

        if label == "table":
            tab_n += 1
            tables.append(
                Table(
                    id=f"tab-{tab_n}",
                    caption=_table_caption(item, doc),
                    section_id=current.id if current else None,
                    rows=_table_rows(item),
                )
            )
            continue

        if label == "picture":
            fig_n += 1
            cap = _table_caption(item, doc)
            figures.append(
                Figure(
                    id=f"fig-{fig_n}",
                    caption=cap,
                    section_id=current.id if current else None,
                )
            )
            continue

        # Regular body text / list_item / code → accumulate paragraph buffer.
        if text:
            para_buf.append(text)

    _flush_paragraph()

    # If Docling produced no sections (very rare; degenerate PDF), fall back to a
    # single 'other' section so atoms/edges can at least attach somewhere.
    if not sections:
        sec_n += 1
        current = Section(id=f"sec-{sec_n}", title="Body", level=1, section_type="other")
        sections.append(current)
        body_text = re.sub(r"\s+", " ", "\n".join(_item_text(i) for i in iter_items())).strip()
        if body_text:
            current.paragraphs.append(
                Paragraph(id=f"{current.id}-p1", text=body_text, citations=_extract_citations(body_text, references, ref_index))
            )

    paper.sections = sections
    paper.equations = equations
    paper.tables = tables
    paper.figures = figures
    paper.references = references
    return paper


# --------------------------------------------------------------------------- #
# Marker (legacy)
# --------------------------------------------------------------------------- #


def _markdown_from_marker(pdf_path: Path) -> str:
    try:
        from marker.converters.pdf import PdfConverter
        from marker.models import create_model_dict
        from marker.output import text_from_rendered
    except ImportError as e:  # noqa: BLE001
        raise ImportError(
            "marker-pdf not installed; legacy backend disabled. "
            "Install with `pip install paper-compiler-cli[pdf-legacy]` or "
            "switch to `parser.pdf_backend = \"docling\"`."
        ) from e

    converter = PdfConverter(artifact_dict=create_model_dict())
    rendered = converter(str(pdf_path))
    text, _, _ = text_from_rendered(rendered)
    return text


def _parse_with_marker(paper: Paper, pdf_path: Path) -> Paper:
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
        citations = _extract_citations(text, references, ref_seen)
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


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #


def _extract_citations(
    text: str,
    references: list[Reference],
    ref_seen: dict[str, str],
) -> list[Citation]:
    """Pull numeric ``[N]`` / ``[N, M]`` citation markers out of body text.

    Appends previously-unseen ref ids to ``references`` so the reference list
    grows as inline citations are encountered (true even when no References
    section was parsed). Symmetric with the marker-path behaviour.
    """
    citations: list[Citation] = []
    for m in _INLINE_CITE_RE.finditer(text):
        for n in re.split(r",\s*", m.group(1)):
            key = f"ref-{n}"
            marker = f"[{n}]"
            if key not in ref_seen:
                ref_seen[key] = key
                references.append(Reference(ref_id=key, marker=marker, raw=marker))
            citations.append(Citation(marker=marker, ref_id=key, context_window=text[:400]))
    return citations
