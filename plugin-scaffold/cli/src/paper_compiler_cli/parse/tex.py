from __future__ import annotations

import re
from pathlib import Path
from typing import Iterator, Optional

try:
    import bibtexparser
except ImportError:  # noqa: BLE001
    bibtexparser = None  # type: ignore[assignment]

from pylatexenc.latex2text import LatexNodes2Text
from pylatexenc.latexwalker import (
    LatexCommentNode,
    LatexEnvironmentNode,
    LatexMacroNode,
    LatexNode,
    LatexWalker,
)

from ..ir import (
    Algorithm,
    Citation,
    Equation,
    Figure,
    Paper,
    Paragraph,
    Reference,
    Section,
    Table,
    classify_section_title,
)

SECTION_MACROS = {"section": 1, "subsection": 2, "subsubsection": 3, "paragraph": 4}
EQUATION_ENVS = {"equation", "equation*", "align", "align*", "gather", "gather*", "multline", "multline*", "eqnarray", "eqnarray*"}
ALGORITHM_ENVS = {"algorithm", "algorithm*", "algorithmic"}
TABLE_ENVS = {"table", "table*", "tabular"}
FIGURE_ENVS = {"figure", "figure*"}
CITE_MACROS = {"cite", "citep", "citet", "citeauthor", "citeyear", "citealp", "autocite", "parencite", "textcite"}

_l2t = LatexNodes2Text()


def _find_main_tex(root: Path) -> Optional[Path]:
    candidates = list(root.rglob("*.tex"))
    if not candidates:
        return None
    for c in candidates:
        try:
            txt = c.read_text(errors="ignore")
        except OSError:
            continue
        if "\\documentclass" in txt and "\\begin{document}" in txt:
            return c
    candidates.sort(key=lambda p: p.stat().st_size, reverse=True)
    return candidates[0]


_INPUT_RE = re.compile(r"\\(?:input|include)\s*\{([^}]+)\}")
_COMMENT_RE = re.compile(r"(?<!\\)%[^\n]*")


def _strip_comments(text: str) -> str:
    return _COMMENT_RE.sub("", text)


def _resolve_input(root: Path, base: Path, name: str) -> Optional[Path]:
    name = name.strip()
    for candidate in (
        base.parent / name,
        base.parent / f"{name}.tex",
        root / name,
        root / f"{name}.tex",
    ):
        if candidate.exists() and candidate.is_file():
            return candidate
    matches = list(root.rglob(Path(name).name + ".tex")) + list(root.rglob(Path(name).name))
    for m in matches:
        if m.is_file():
            return m
    return None


def _expand_inputs(main: Path, root: Path, max_depth: int = 6) -> str:
    seen: set[Path] = set()

    def expand(path: Path, depth: int) -> str:
        try:
            raw = path.read_text(errors="ignore")
        except OSError:
            return ""
        text = _strip_comments(raw)
        if depth <= 0:
            return text
        resolved = path.resolve()
        if resolved in seen:
            return ""
        seen.add(resolved)

        def sub(match: re.Match) -> str:
            name = match.group(1)
            child = _resolve_input(root, path, name)
            if child is None:
                return ""
            return "\n" + expand(child, depth - 1) + "\n"

        return _INPUT_RE.sub(sub, text)

    return expand(main, max_depth)


_BBL_THEBIB_RE = re.compile(r"\\bibitem(?:\[[^\]]*\])?\s*\{([^}]+)\}", re.MULTILINE)
_BBL_ENTRY_RE = re.compile(r"\\bibitem(?:\[[^\]]*\])?\s*\{([^}]+)\}(.*?)(?=\\bibitem|\\end\{thebibliography\})", re.DOTALL)


def _load_thebibliography(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in _BBL_ENTRY_RE.finditer(text):
        key = m.group(1).strip()
        body = re.sub(r"\s+", " ", m.group(2)).strip().strip(".")
        out[key] = body
    return out


def _load_bib(root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if bibtexparser is None:
        return out
    for bib in root.rglob("*.bib"):
        try:
            db = bibtexparser.parse_file(str(bib)) if hasattr(bibtexparser, "parse_file") else bibtexparser.bibtexparser.parse_file(str(bib))  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            try:
                with open(bib, encoding="utf-8", errors="ignore") as fh:
                    parsed = bibtexparser.load(fh)
                for ent in parsed.entries:
                    out[ent.get("ID", "")] = " ".join(f"{k}={v}" for k, v in ent.items() if k != "ID")
                continue
            except Exception:  # noqa: BLE001
                continue
        for ent in getattr(db, "entries", []) or []:
            key = getattr(ent, "key", None) or (ent.get("ID") if isinstance(ent, dict) else None)
            if not key:
                continue
            fields = {}
            if hasattr(ent, "fields_dict"):
                fields = {k: str(v.value) for k, v in ent.fields_dict.items()}
            elif isinstance(ent, dict):
                fields = {k: v for k, v in ent.items() if k != "ID"}
            raw = " ".join(f"{k}={v}" for k, v in fields.items())
            out[key] = raw
    return out


def _iter_nodes(nodes: list[LatexNode]) -> Iterator[LatexNode]:
    for n in nodes:
        yield n
        if isinstance(n, LatexEnvironmentNode):
            yield from _iter_nodes(n.nodelist)


def _macro_text(node: LatexMacroNode) -> str:
    args = node.nodeargd.argnlist if node.nodeargd else []
    parts = []
    for a in args:
        if a is None:
            continue
        try:
            parts.append(_l2t.nodelist_to_text([a]))
        except Exception:  # noqa: BLE001
            continue
    return " ".join(p for p in parts if p)


def _cite_keys(node: LatexMacroNode) -> list[str]:
    args = node.nodeargd.argnlist if node.nodeargd else []
    if not args:
        return []
    for a in reversed(args):
        if a is None:
            continue
        try:
            text = _l2t.nodelist_to_text([a])
        except Exception:  # noqa: BLE001
            continue
        text = text.strip().strip("{}")
        if text:
            return [k.strip() for k in text.split(",") if k.strip()]
    return []


def _nodes_to_text(nodes: list[LatexNode]) -> str:
    try:
        return _l2t.nodelist_to_text(nodes)
    except Exception:  # noqa: BLE001
        return ""


def parse_tex(paper: Paper, root: Path) -> Paper:
    main = _find_main_tex(root)
    if main is None:
        return paper
    source = _expand_inputs(main, root)
    bib = _load_bib(root)
    bib.update(_load_thebibliography(source))

    walker = LatexWalker(source)
    nodes, _, _ = walker.get_latex_nodes()

    sections: list[Section] = []
    equations: list[Equation] = []
    algorithms: list[Algorithm] = []
    tables: list[Table] = []
    figures: list[Figure] = []
    references: list[Reference] = []
    ref_index: dict[str, str] = {}

    current_section: Optional[Section] = None
    current_para: list[LatexNode] = []
    eq_count = 0
    alg_count = 0
    tab_count = 0
    fig_count = 0
    para_count = 0
    sec_count = 0

    def flush_paragraph() -> None:
        nonlocal current_para, para_count
        if not current_para or current_section is None:
            current_para = []
            return
        text = _nodes_to_text(current_para)
        cleaned = re.sub(r"\s+", " ", text).strip()
        if not cleaned:
            current_para = []
            return
        para_count += 1
        pid = f"{current_section.id}-p{para_count}"
        citations: list[Citation] = []
        for n in _iter_nodes(current_para):
            if isinstance(n, LatexMacroNode) and n.macroname in CITE_MACROS:
                for key in _cite_keys(n):
                    if key not in ref_index:
                        ref_id = f"ref-{len(references) + 1}"
                        ref_index[key] = ref_id
                        references.append(
                            Reference(
                                ref_id=ref_id,
                                marker=f"[{key}]",
                                raw=bib.get(key, key),
                            )
                        )
                    citations.append(
                        Citation(
                            marker=f"[{key}]",
                            ref_id=ref_index[key],
                            context_window=cleaned[:400],
                        )
                    )
        eq_refs = [e.id for e in equations if e.section_id == current_section.id and pid in e.mentioned_in]
        current_section.paragraphs.append(
            Paragraph(id=pid, text=cleaned, citations=citations, equation_refs=eq_refs)
        )
        current_para = []

    def open_section(level: int, title: str) -> None:
        nonlocal current_section, sec_count, para_count
        flush_paragraph()
        sec_count += 1
        para_count = 0
        sid = f"sec-{sec_count}"
        sec = Section(id=sid, title=title, level=level, section_type=classify_section_title(title))
        sections.append(sec)
        current_section = sec

    for node in nodes:
        if isinstance(node, LatexCommentNode):
            continue
        if isinstance(node, LatexMacroNode) and node.macroname in SECTION_MACROS:
            title = _macro_text(node)
            open_section(SECTION_MACROS[node.macroname], title or node.macroname)
            continue
        if isinstance(node, LatexEnvironmentNode):
            env = node.environmentname
            if env in EQUATION_ENVS:
                eq_count += 1
                latex = node.latex_verbatim()
                section_id = current_section.id if current_section else None
                pid_anchor = f"{section_id}-p{max(para_count, 1)}" if section_id else None
                equations.append(
                    Equation(
                        id=f"eq-{eq_count}",
                        latex=latex,
                        section_id=section_id,
                        mentioned_in=[pid_anchor] if pid_anchor else [],
                    )
                )
                continue
            if env in ALGORITHM_ENVS:
                alg_count += 1
                algorithms.append(
                    Algorithm(
                        id=f"alg-{alg_count}",
                        title=None,
                        pseudocode=node.latex_verbatim(),
                        section_id=current_section.id if current_section else None,
                    )
                )
                continue
            if env in TABLE_ENVS:
                tab_count += 1
                caption_text = ""
                for sub in _iter_nodes(node.nodelist):
                    if isinstance(sub, LatexMacroNode) and sub.macroname == "caption":
                        caption_text = _macro_text(sub)
                        break
                tables.append(
                    Table(
                        id=f"tab-{tab_count}",
                        caption=caption_text,
                        section_id=current_section.id if current_section else None,
                    )
                )
                continue
            if env in FIGURE_ENVS:
                fig_count += 1
                caption_text = ""
                for sub in _iter_nodes(node.nodelist):
                    if isinstance(sub, LatexMacroNode) and sub.macroname == "caption":
                        caption_text = _macro_text(sub)
                        break
                figures.append(
                    Figure(
                        id=f"fig-{fig_count}",
                        caption=caption_text,
                        section_id=current_section.id if current_section else None,
                    )
                )
                continue
            if env == "document":
                inner = node.nodelist
                inner_para: list[LatexNode] = []
                for sub in inner:
                    if isinstance(sub, LatexCommentNode):
                        continue
                    if isinstance(sub, LatexMacroNode) and sub.macroname in SECTION_MACROS:
                        if inner_para:
                            current_para.extend(inner_para)
                            flush_paragraph()
                            inner_para = []
                        title = _macro_text(sub) or sub.macroname
                        open_section(SECTION_MACROS[sub.macroname], title)
                    elif isinstance(sub, LatexEnvironmentNode) and sub.environmentname in EQUATION_ENVS:
                        eq_count += 1
                        latex = sub.latex_verbatim()
                        section_id = current_section.id if current_section else None
                        pid_anchor = f"{section_id}-p{max(para_count + 1, 1)}" if section_id else None
                        equations.append(
                            Equation(id=f"eq-{eq_count}", latex=latex, section_id=section_id, mentioned_in=[pid_anchor] if pid_anchor else [])
                        )
                    elif isinstance(sub, LatexEnvironmentNode) and sub.environmentname in ALGORITHM_ENVS:
                        alg_count += 1
                        algorithms.append(Algorithm(id=f"alg-{alg_count}", title=None, pseudocode=sub.latex_verbatim(), section_id=current_section.id if current_section else None))
                    else:
                        inner_para.append(sub)
                        if isinstance(sub, LatexMacroNode) and sub.macroname == "par":
                            current_para.extend(inner_para)
                            flush_paragraph()
                            inner_para = []
                if inner_para:
                    current_para.extend(inner_para)
                    flush_paragraph()
                continue
        current_para.append(node)

    flush_paragraph()

    paper.sections = sections
    paper.equations = equations
    paper.algorithms = algorithms
    paper.tables = tables
    paper.figures = figures
    paper.references = references
    return paper
