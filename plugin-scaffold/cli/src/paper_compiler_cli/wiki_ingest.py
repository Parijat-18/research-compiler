"""Re-embed `research/wiki/answers/*.md` back into the retrieval store.

Closes the v0.2 audit's "wiki is dead artifact" loop: promoted answers
(written by `wiki-query`) survive across rebuilds but were never indexed,
so each session re-discovered the same cross-paper insights.

This module scans the answers directory on every compile, ingests each
file into the new ``wiki_answers`` table (Phase 1 schema), then writes the
body into ``chunks_fts`` + ``chunks_vec`` with ``chunk_kind="answer"``
(Phase 6 taxonomy). After this pass, ``query_chunks(q)`` finds promoted
answers naturally — the same retrieval surface as paper text.

Answer file format (loose; the frontmatter is optional):

    ---
    slug: jepa-vs-ijepa-loss
    source_atom_uids: [abc123def456, deadbeef0001]
    created_at: 2026-05-19T00:00:00Z
    ---

    # How does JEPA's loss differ from I-JEPA's?
    ...body markdown...

Slug defaults to the filename stem when frontmatter is absent.
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Optional


_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
_LIST_RE = re.compile(r"\[(.*?)\]")


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Pull a YAML-ish frontmatter block off the head of ``text``.

    We deliberately don't pull in a YAML dep — answer-file frontmatter is
    a handful of scalar/list fields. Returns ``({...}, body_without_fm)``.
    """
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    body = text[m.end() :]
    fm: dict = {}
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            inner = _LIST_RE.search(value).group(1)  # type: ignore[union-attr]
            fm[key] = [x.strip().strip("'\"") for x in inner.split(",") if x.strip()]
        else:
            fm[key] = value.strip("'\"")
    return fm, body


def _embed_one_text(text: str, vec_dim: int):
    """Embed a single string with the same bge-small model used elsewhere.

    Returns None on any failure so callers can degrade to BM25-only
    retrieval over the answer rather than refusing to index it.
    """
    try:
        from sentence_transformers import SentenceTransformer
        import numpy as np
    except ImportError:
        return None
    try:
        model = SentenceTransformer("BAAI/bge-small-en-v1.5")
        vec = model.encode([text], normalize_embeddings=True, show_progress_bar=False)[0]
        return np.asarray(vec, dtype="float32")
    except Exception as e:  # noqa: BLE001
        print(f"wiki-answer embed failed: {e}", file=sys.stderr)
        return None


def reembed_wiki_answers(conn, research_dir: Path, *, vec_loaded: bool) -> dict:
    """Ingest every promoted answer back into ``wiki_answers`` + chunks index.

    Returns a stats dict ``{"answers": N, "embedded": E}`` for the build
    manifest. Safe to call when the answers directory is missing.
    """
    answers_dir = research_dir / "wiki" / "answers"
    if not answers_dir.exists():
        return {"answers": 0, "embedded": 0}

    # Wipe stale rows so renamed/deleted answers don't linger.
    conn.execute("DELETE FROM wiki_answers")
    conn.execute("DELETE FROM chunks_fts WHERE rowid IN (SELECT chunk_id FROM chunks WHERE chunk_kind = 'answer')")
    if vec_loaded:
        try:
            conn.execute("DELETE FROM chunks_vec WHERE rowid IN (SELECT chunk_id FROM chunks WHERE chunk_kind = 'answer')")
        except Exception:  # noqa: BLE001
            pass
    conn.execute("DELETE FROM chunks WHERE chunk_kind = 'answer'")

    n = 0
    embedded = 0
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    for path in sorted(answers_dir.glob("*.md")):
        if path.name == "README.md":
            continue
        raw = path.read_text(encoding="utf-8")
        if not raw.strip():
            continue
        fm, body = _parse_frontmatter(raw)
        slug = fm.get("slug") or path.stem
        source_uids = fm.get("source_atom_uids") or []
        if isinstance(source_uids, str):
            source_uids = [source_uids]
        answer_id = f"answer:{slug}"

        # 1. Persist the structured row.
        conn.execute(
            """
            INSERT OR REPLACE INTO wiki_answers(answer_id, slug, body_md, source_atom_uids, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                answer_id,
                slug,
                body.strip(),
                json.dumps(list(source_uids)),
                fm.get("created_at") or now,
                now,
            ),
        )

        # 2. Insert into chunks with chunk_kind="answer" so query_chunks
        # finds it naturally. paper_id stays NULL (the FK allows NULL),
        # section_id stays NULL, paragraph_id stores the slug for human
        # reference. Quality is 0.80 (high — promoted answers are signal).
        text = body.strip()
        cur = conn.execute(
            """
            INSERT INTO chunks(paper_id, section_id, paragraph_id, ord, text, n_tokens,
                                is_indexed, quality, chunk_kind)
            VALUES (NULL, NULL, ?, 0, ?, ?, 1, 0.80, 'answer')
            """,
            (slug, text, len(text) // 4),
        )
        chunk_id = cur.lastrowid
        n += 1

        # 3. Index in FTS5 + vec0 so retrieval surfaces it.
        conn.execute(
            "INSERT INTO chunks_fts(rowid, text) VALUES (?, ?)",
            (chunk_id, text),
        )
        if vec_loaded:
            vec = _embed_one_text(text, vec_dim=384)
            if vec is not None:
                import struct
                blob = struct.pack(f"{len(vec)}f", *[float(x) for x in vec])
                try:
                    conn.execute(
                        "INSERT INTO chunks_vec(rowid, embedding) VALUES (?, ?)",
                        (chunk_id, blob),
                    )
                    embedded += 1
                except Exception as e:  # noqa: BLE001
                    print(f"chunks_vec insert failed for {slug}: {e}", file=sys.stderr)

    print(f"wiki-ingest: {n} answers re-embedded ({embedded} with vec)", file=sys.stderr)
    return {"answers": n, "embedded": embedded}
