"""Persist atom embeddings for the MCP server's vector search.

Writes ``research/embeddings.npy`` (float32 matrix) + ``research/embeddings.json``
(atom-id index) when an embedder is available. Otherwise no-op — the MCP server
falls back to BM25.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from ..atoms import Atom, EvidenceSpan


def _load_embedder():
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        return None, None
    # 384-dim first so it matches the DB schema (chunks_vec, atoms_vec).
    for name in ("BAAI/bge-small-en-v1.5", "allenai-specter"):
        try:
            return SentenceTransformer(name), name
        except Exception:  # noqa: BLE001
            continue
    return None, None


def _atom_text(atom: Atom, evidence_by_id: dict[str, EvidenceSpan]) -> str:
    parts = [atom.name, atom.category, atom.description or ""]
    for eid in atom.evidence_span_ids[:2]:
        ev = evidence_by_id.get(eid)
        if ev:
            parts.append(ev.verbatim_text[:500])
    return " ".join(parts)


def write_embeddings(research_dir: Path, atoms: list[Atom], evidence: list[EvidenceSpan]) -> bool:
    if not atoms:
        return False
    model, model_name = _load_embedder()
    if model is None:
        print("embeddings: sentence-transformers not installed; skipping vector index", file=sys.stderr)
        return False
    try:
        import numpy as np
    except ImportError:
        return False

    evidence_by_id = {e.id: e for e in evidence}
    texts = [_atom_text(a, evidence_by_id) for a in atoms]
    vecs = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    arr = np.asarray(vecs, dtype="float32")
    research_dir.mkdir(parents=True, exist_ok=True)
    np.save(research_dir / "embeddings.npy", arr)
    (research_dir / "embeddings.json").write_text(
        json.dumps({"atom_ids": [a.id for a in atoms], "model": model_name}, indent=2)
    )
    print(f"embeddings: {arr.shape} via {model_name}", file=sys.stderr)
    return True
