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

    Heuristics, in priority order:
      1. Letter density (`[A-Za-z]` / total len). High prose ≥ 0.65.
      2. Average word length and word count. Real paragraphs have ≥ 25 words.
      3. Punctuation rate. Table rows tend to be `|`-, `-`-, `&`-heavy.
      4. Numeric density. >25% digits + dots is almost always tabular.
    """
    if not text:
        return 0.0
    n = len(text)
    if n < 60:
        return 0.0
    letters = sum(1 for c in text if c.isalpha())
    digits = sum(1 for c in text if c.isdigit())
    punct_table = sum(1 for c in text if c in "|&\\")
    letter_ratio = letters / n
    digit_ratio = digits / n
    table_punct_ratio = punct_table / n
    words = [w for w in re.split(r"\s+", text) if len(w) > 1]
    word_count = len(words)
    avg_word_len = sum(len(w) for w in words) / max(word_count, 1)

    # Hard fails — these never pass.
    if letter_ratio < 0.5:
        return 0.0
    if digit_ratio > 0.25:
        return 0.0
    if table_punct_ratio > 0.04:
        return 0.0
    if word_count < 20:
        return 0.0
    if avg_word_len > 12 or avg_word_len < 3:
        # Avg too high → likely glued-up tokens / formulas. Too low → punctuation row.
        return 0.0

    # Softer scoring on top.
    score = 0.5 * min(1.0, (letter_ratio - 0.5) / 0.4) + 0.3 * min(1.0, word_count / 100.0)
    score += 0.2 * (1.0 - min(1.0, digit_ratio / 0.25))
    return round(min(1.0, max(0.0, score)), 3)


def is_indexable(section_type: str | None, section_title: str | None, text: str) -> tuple[bool, float]:
    """Decide whether a chunk should be inserted into ``chunks_fts``.

    Returns (is_indexed, quality_score). Even non-indexed chunks are stored in
    `chunks` for traceability via ``chunk_id`` — they just don't appear in
    text search.
    """
    quality = prose_quality(text)
    if quality == 0.0:
        return False, 0.0
    if section_type in (None, "appendix", "other") and not is_method_adjacent_title(section_title):
        return False, quality
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
