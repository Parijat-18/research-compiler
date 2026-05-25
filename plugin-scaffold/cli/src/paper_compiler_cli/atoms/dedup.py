"""Atom deduplication.

Per-paragraph extraction yields many near-duplicates of the same concept
(e.g. an ML paper might emit "ViT encoder", "Vision Transformer encoder",
"ViT" as three atoms; a chemistry paper might emit "Heck coupling",
"Heck cross-coupling reaction"). Three passes:

1. **Exact normalize**: strip punctuation, lowercase, sort tokens. Merge.
2. **Jaccard / containment**: pair atoms with token overlap above a threshold
   AND matching category. Merge.
3. **Embedding cosine** (optional): if a sentence-transformer embedder is
   available, merge atoms in the same category with cosine ≥ the
   per-category threshold.

Per-category dedup thresholds (domain-neutral):
- ``data`` is strict (0.95) — named samples / datasets / measurement sets
  should NOT collapse ("ImageNet" vs "ImageNet-21k", "GTEx v8" vs "GTEx v6").
- ``method`` is loose (0.85) — named methods have many surface forms
  ("ViT" / "Vision Transformer / "ViT-B/16", or "Heck coupling" / "Mizoroki-Heck
  reaction").
- ``objective``, ``procedure``, ``preprocessing`` sit in the middle.
- Default: 0.88.

Merging strategy: keep the highest-priority atom, fold ``used_by_paper_ids``,
``evidence_span_ids``, and ``dependencies`` into it.
"""

from __future__ import annotations

import re
import sys
from typing import Iterable, Optional

from . import Atom

# Per-category cosine thresholds (domain-neutral). Strict for *data* and
# *baseline* (distinct named datasets / reference methods must stay
# separate); loose for *method* (surface-form variation is high across
# domains); medium elsewhere.
DEDUP_COSINE_BY_CATEGORY: dict[str, float] = {
    "data": 0.95,
    "evaluation": 0.92,
    "baseline": 0.92,
    "method": 0.85,
    "objective": 0.88,
    "procedure": 0.90,
    "parameter": 0.90,
    "preprocessing": 0.88,
    "theory": 0.92,
}
DEDUP_COSINE_DEFAULT: float = 0.88

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")
_STOPWORDS = {
    "a", "an", "the", "of", "for", "and", "or", "to", "in", "on", "with",
    "module", "layer", "based", "type", "version",
}


def _tokens(name: str) -> frozenset[str]:
    return frozenset(t.lower() for t in _TOKEN_RE.findall(name) if t.lower() not in _STOPWORDS)


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union


def _containment(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def _merge(into: Atom, other: Atom) -> None:
    for pid in other.used_by_paper_ids:
        if pid not in into.used_by_paper_ids:
            into.used_by_paper_ids.append(pid)
    for eid in other.evidence_span_ids:
        if eid not in into.evidence_span_ids:
            into.evidence_span_ids.append(eid)
    for d in other.dependencies:
        if d not in into.dependencies:
            into.dependencies.append(d)
    if other.priority > into.priority:
        into.priority = other.priority
    if len(other.description or "") > len(into.description or ""):
        into.description = other.description


def _exact_normalize(atoms: list[Atom]) -> list[Atom]:
    seen: dict[tuple[str, frozenset[str]], Atom] = {}
    out: list[Atom] = []
    for a in atoms:
        key = (a.category, _tokens(a.name))
        if key in seen:
            _merge(seen[key], a)
            continue
        seen[key] = a
        out.append(a)
    return out


def _jaccard_pass(atoms: list[Atom], threshold: float = 0.6, containment_threshold: float = 0.85) -> list[Atom]:
    out: list[Atom] = []
    out_tokens: list[frozenset[str]] = []
    for a in atoms:
        toks = _tokens(a.name)
        merged = False
        for i, existing in enumerate(out):
            if existing.category != a.category:
                continue
            j = _jaccard(out_tokens[i], toks)
            c = _containment(out_tokens[i], toks)
            if j >= threshold or c >= containment_threshold:
                _merge(existing, a)
                merged = True
                break
        if not merged:
            out.append(a)
            out_tokens.append(toks)
    return out


def _embedding_pass(atoms: list[Atom], threshold: Optional[float] = None) -> list[Atom]:
    """Cosine-similarity merge within each category.

    Phase 5: ``threshold`` is per-category by default
    (``DEDUP_COSINE_BY_CATEGORY``). Passing an explicit float overrides it
    globally — used in tests and for back-compat.
    """
    if len(atoms) < 4:
        return atoms
    try:
        from sentence_transformers import SentenceTransformer  # noqa: F401
    except ImportError:
        return atoms
    try:
        import numpy as np
        from sentence_transformers import SentenceTransformer
    except ImportError:
        return atoms

    model = _try_load_embedder()
    if model is None:
        return atoms

    texts = [f"{a.name}. {a.description}" for a in atoms]
    vecs = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    out: list[Atom] = []
    out_vecs: list = []  # noqa: ANN401
    for i, a in enumerate(atoms):
        merged = False
        for j, existing in enumerate(out):
            if existing.category != a.category:
                continue
            sim = float(np.dot(out_vecs[j], vecs[i]))
            cat_threshold = (
                threshold
                if threshold is not None
                else DEDUP_COSINE_BY_CATEGORY.get(a.category, DEDUP_COSINE_DEFAULT)
            )
            if sim >= cat_threshold:
                _merge(existing, a)
                merged = True
                break
        if not merged:
            out.append(a)
            out_vecs.append(vecs[i])
    return out


def _try_load_embedder():
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        return None
    for name in ("BAAI/bge-small-en-v1.5", "allenai-specter"):
        try:
            return SentenceTransformer(name)
        except Exception:  # noqa: BLE001
            continue
    return None


def deduplicate(atoms: list[Atom], *, embedding_threshold: Optional[float] = None) -> list[Atom]:
    """Three-pass dedup. ``embedding_threshold=None`` means per-category."""
    before = len(atoms)
    atoms = _exact_normalize(atoms)
    atoms = _jaccard_pass(atoms)
    atoms = _embedding_pass(atoms, threshold=embedding_threshold)
    print(f"dedup: {before} → {len(atoms)} atoms", file=sys.stderr)
    return atoms
