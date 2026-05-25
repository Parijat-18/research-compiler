"""Shared text utilities: placeholder scrubbing + prose quality scoring.

These functions are the single source of truth for "is this text high-signal
enough to index and retrieve, and if so, in what form?" Used by both the chunker
in `graph_db.py` and the atom extractor in `atoms/extract.py`.
"""

from __future__ import annotations

import re

# Markdown / LaTeX artifacts left by parsers that we never want to retrieve.
_PLACEHOLDER_RES = [
    re.compile(r"<\s*g\s*r\s*a\s*p\s*h\s*i\s*c\s*s\s*>"),  # Marker figure placeholder.
    re.compile(r"<\s*cit\.?\s*>"),
    re.compile(r"\\includegraphics\b[^\}]*\}"),
    re.compile(r"\\ref\{[^\}]+\}"),
    re.compile(r"\\eqref\{[^\}]+\}"),
    re.compile(r"\\label\{[^\}]+\}"),
]

# Section titles we'll always index even when section_type isn't "method".
_METHOD_ADJACENT_KEYWORDS = (
    "method",
    "approach",
    "architecture",
    "model",
    "framework",
    "algorithm",
    "training",
    "loss",
    "objective",
    "optimization",
    "implementation",
    "preprocess",
    "dataset",
    "experiment",
    "evaluation",
    "metric",
    "ablation",
    "result",
)


def scrub_placeholders(text: str) -> str:
    """Strip LaTeX / Marker placeholders. Collapse whitespace."""
    if not text:
        return ""
    for r in _PLACEHOLDER_RES:
        text = r.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def is_method_adjacent_title(title: str | None) -> bool:
    if not title:
        return False
    low = title.lower()
    return any(k in low for k in _METHOD_ADJACENT_KEYWORDS)


def prose_quality(text: str) -> float:
    """Return a 0..1 score for "looks like English prose" vs table/equation noise.

    Phase 6: returns a soft score in [0.05, 1.0] for any non-empty text. The
    previous hard-fail thresholds (60% chunk dropout in the JEPA audit) are
    gone — every chunk gets indexed and retrieval uses ``chunk_kind`` + a
    quality weight to rank, not to drop. Tables/captions/references are NOT
    judged by this prose-prior function; they receive default quality scores
    keyed off ``chunk_kind`` in ``classify_chunk_kind``.
    """
    if not text:
        return 0.0
    n = len(text)
    if n < 20:
        return 0.05
    letters = sum(1 for c in text if c.isalpha())
    digits = sum(1 for c in text if c.isdigit())
    punct_table = sum(1 for c in text if c in "|&\\")
    letter_ratio = letters / n
    digit_ratio = digits / n
    table_punct_ratio = punct_table / n
    words = [w for w in re.split(r"\s+", text) if len(w) > 1]
    word_count = len(words)
    avg_word_len = sum(len(w) for w in words) / max(word_count, 1)

    # Soft scoring: lower scores for tabular / numeric / very-short text, but
    # we never zero anything out — retrieval is allowed to find low-prose
    # chunks when the user explicitly asks for tables / numerics via
    # ``prefer_kind`` or when the query itself is keyword-precise.
    score = 0.5 * min(1.0, (letter_ratio - 0.3) / 0.4)
    score += 0.3 * min(1.0, word_count / 100.0)
    score += 0.2 * (1.0 - min(1.0, digit_ratio / 0.5))
    score -= 0.4 * min(1.0, table_punct_ratio / 0.05)
    if avg_word_len > 14 or avg_word_len < 2.5:
        score -= 0.2
    return round(min(1.0, max(0.05, score)), 3)


# Phase 6: chunk taxonomy. Recorded on each row so retrieval can filter
# (e.g. ``query_chunks(kinds=["table"])``) or boost via ``prefer_kind``.
CHUNK_KINDS = (
    "prose",          # body paragraph of text
    "table",          # table caption + serialized rows (if available)
    "caption",        # figure caption (no body text)
    "reference",      # bibliography entry
    "equation_block", # display equation or block with $$...$$
    "answer",         # promoted wiki/answers/* content (Phase 8)
)

# Default quality assignments for non-prose kinds. Prose chunks use
# prose_quality() directly. The numbers below are intentionally mid-range:
# they're floors, not penalties, so a table or caption can still surface
# when the BM25/dense score is high.
_DEFAULT_QUALITY_BY_KIND = {
    "table": 0.55,
    "caption": 0.45,
    "reference": 0.30,
    "equation_block": 0.50,
    "answer": 0.80,  # promoted answers are high-signal by construction
}

# Patterns that flip a paragraph chunk away from "prose" without the
# parser having to tell us. Cheap; lets us catch reference list items and
# bare equation blocks that slip through as paragraphs.
_EQUATION_BLOCK_RE = re.compile(r"\$\$.+?\$\$|\\begin\{(equation|align|gather)\*?\}", re.DOTALL)
_REF_ENTRY_RE = re.compile(r"^\s*\[\d{1,3}\]\s+\S")


def classify_chunk_kind(
    section_type: str | None,
    section_title: str | None,
    text: str,
    *,
    override_kind: str | None = None,
) -> tuple[str, float]:
    """Return ``(chunk_kind, quality)`` for a piece of indexable text.

    Callers ingesting structured items (tables, figures, equations) pass
    ``override_kind`` so the heuristics below stay focused on body
    paragraphs. The quality for override kinds comes from
    ``_DEFAULT_QUALITY_BY_KIND``; for prose it comes from
    ``prose_quality(text)``.
    """
    if override_kind:
        return override_kind, _DEFAULT_QUALITY_BY_KIND.get(override_kind, 0.5)

    # Reference list entries (numeric-marker prefix).
    title_low = (section_title or "").lower()
    if "reference" in title_low or "bibliograph" in title_low:
        return "reference", _DEFAULT_QUALITY_BY_KIND["reference"]
    if _REF_ENTRY_RE.match(text or ""):
        return "reference", _DEFAULT_QUALITY_BY_KIND["reference"]

    # Display equation paragraphs that the parser left in the body stream.
    if text and _EQUATION_BLOCK_RE.search(text):
        return "equation_block", _DEFAULT_QUALITY_BY_KIND["equation_block"]

    # Everything else is prose; quality from the soft prior.
    return "prose", prose_quality(text or "")


def is_indexable(section_type: str | None, section_title: str | None, text: str) -> tuple[bool, float]:
    """Deprecated v0.2 entrypoint. Phase 6 indexes every chunk.

    Returns ``(True, quality)`` so callers that haven't been migrated to
    ``classify_chunk_kind`` still record a sensible quality score and keep
    indexing. ``is_indexed`` stays in the schema for one release and
    defaults to 1 (Phase 8 drops it).
    """
    _, quality = classify_chunk_kind(section_type, section_title, text)
    return True, quality


def split_with_overlap(text: str, *, target_chars: int = 750, overlap_chars: int = 200) -> list[str]:
    """Split long text into overlapping windows of roughly ``target_chars``.

    Splits prefer sentence boundaries. Used when a paragraph is too long for a
    single chunk window. Keeps adjacent chunks reading well even after slicing.
    """
    text = text.strip()
    if len(text) <= target_chars:
        return [text]
    sentences = re.split(r"(?<=[.!?])\s+", text)
    out: list[str] = []
    cur: list[str] = []
    cur_len = 0
    for sent in sentences:
        if cur_len + len(sent) > target_chars and cur:
            out.append(" ".join(cur).strip())
            # carry overlap by re-emitting the trailing characters of the last chunk
            tail = out[-1][-overlap_chars:] if overlap_chars > 0 else ""
            cur = [tail, sent] if tail else [sent]
            cur_len = sum(len(x) for x in cur)
        else:
            cur.append(sent)
            cur_len += len(sent) + 1
    if cur:
        out.append(" ".join(cur).strip())
    # de-dup pure-substring overlaps that the tail trick can produce
    deduped: list[str] = []
    for chunk in out:
        if not deduped:
            deduped.append(chunk)
            continue
        if chunk.startswith(deduped[-1][-overlap_chars:]) and chunk in deduped[-1]:
            continue
        deduped.append(chunk)
    return deduped
