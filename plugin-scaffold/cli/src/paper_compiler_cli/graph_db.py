"""Graph RAG database — single sqlite file with sqlite-vec + FTS5.

Layout (one ``research/research.db`` per compile):

    papers(paper_id PK, title, year, venue, authors_json, abstract,
           rank, scholarly_influence, implementation_influence,
           is_target, depth, acquired, parsed_path)

    sections(section_id PK, paper_id FK, title, section_type, ord)

    chunks(chunk_id PK, paper_id FK, section_id FK NULL,
           paragraph_id, ord, text, n_tokens)

    chunks_fts -- FTS5 virtual table over chunks.text + paper title.

    chunks_vec -- vec0 virtual table, 384-dim float embeddings keyed by chunk_id.

    atoms(atom_id PK, name, category, defined_by_paper_id FK,
          description, priority)

    atoms_fts -- FTS5 over atoms.name + atoms.description.

    atom_paper_usage(atom_id FK, paper_id FK, role) -- many-to-many.

    atom_evidence(atom_id FK, chunk_id FK, evidence_id) -- backing spans.

    edges(edge_id PK, from_paper_id FK, to_paper_id FK,
          best_role, best_confidence, section_type, paragraph_id,
          classifier, context)

    edge_roles(edge_id FK, label, confidence) -- multi-label.

    equations(equation_id PK, paper_id FK, section_id, latex)

    communities(community_id PK, label, summary, size)

    community_papers(community_id FK, paper_id FK)
    community_atoms(community_id FK, atom_id FK)

    missing_details(md_id PK, question, category, options_json,
                    suggested_default, rationale)

Indices: every FK has its own index. FTS5 indices are built incrementally.

Why sqlite? Single-file artifact, zero-daemon, queryable from any MCP tool
without an extra service, ships in the user's repo alongside research.md.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import Iterable, Optional

SCHEMA_VERSION = "2.0"

# Each chunk is a paragraph or a small window of paragraphs (cap at ~512 tokens
# approximated by char count). We keep raw text in the chunks table and index it
# both in FTS5 (lexical) and vec0 (semantic).
CHUNK_CHAR_BUDGET = 1800


def _try_load_vec(conn: sqlite3.Connection) -> bool:
    try:
        import sqlite_vec
    except ImportError:
        return False
    try:
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        return True
    except (sqlite3.OperationalError, AttributeError) as e:
        print(f"sqlite-vec load failed (no extension support): {e}", file=sys.stderr)
        return False


def open_db(path: Path) -> tuple[sqlite3.Connection, bool]:
    """Open / create the graph DB. Returns (conn, vec_loaded)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    vec_loaded = _try_load_vec(conn)
    return conn, vec_loaded


def init_schema(conn: sqlite3.Connection, vec_loaded: bool, vec_dim: int = 384) -> None:
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS papers (
            paper_id TEXT PRIMARY KEY,
            title TEXT,
            year INTEGER,
            venue TEXT,
            authors_json TEXT,
            abstract TEXT,
            rank REAL,
            scholarly_influence REAL,
            implementation_influence REAL,
            is_target INTEGER DEFAULT 0,
            depth INTEGER,
            acquired INTEGER DEFAULT 0,
            -- Phase 3: which source produced this paper's full text
            -- (one of arxiv_tex, arxiv_pdf, s2_pdf, openalex_pdf,
            -- unpaywall_pdf, crossref_pdf, local_pdf, NULL if unacquired).
            acquired_via TEXT,
            parsed_path TEXT
        );
        CREATE INDEX IF NOT EXISTS ix_papers_acquired_via ON papers(acquired_via);

        CREATE TABLE IF NOT EXISTS sections (
            section_id TEXT PRIMARY KEY,
            paper_id TEXT REFERENCES papers(paper_id),
            title TEXT,
            section_type TEXT,
            ord INTEGER
        );
        CREATE INDEX IF NOT EXISTS ix_sections_paper ON sections(paper_id);

        CREATE TABLE IF NOT EXISTS chunks (
            chunk_id INTEGER PRIMARY KEY AUTOINCREMENT,
            paper_id TEXT REFERENCES papers(paper_id),
            section_id TEXT REFERENCES sections(section_id),
            paragraph_id TEXT,
            ord INTEGER,
            text TEXT,
            n_tokens INTEGER,
            -- Phase 6: index-everything. ``is_indexed`` stays for one
            -- release for backward compatibility but is always 1 — every
            -- chunk gets written to chunks_fts and chunks_vec. Retrieval
            -- filters on ``chunk_kind`` instead.
            is_indexed INTEGER DEFAULT 1,
            quality REAL DEFAULT 1.0,
            -- Phase 6: chunk taxonomy. One of: prose, table, caption,
            -- reference, equation_block, answer. Drives retrieval
            -- filtering (``query_chunks(kinds=...)``) and ranking
            -- (``prefer_kind=...``). Assigned by
            -- text_utils.classify_chunk_kind.
            chunk_kind TEXT DEFAULT 'prose'
        );
        CREATE INDEX IF NOT EXISTS ix_chunks_paper ON chunks(paper_id);
        CREATE INDEX IF NOT EXISTS ix_chunks_section ON chunks(section_id);
        CREATE INDEX IF NOT EXISTS ix_chunks_indexed ON chunks(is_indexed);
        CREATE INDEX IF NOT EXISTS ix_chunks_kind ON chunks(chunk_kind);
        -- (paper_id, paragraph_id) is the lookup key when resolving
        -- atom_evidence.chunk_id from an EvidenceSpan during ingest.
        CREATE INDEX IF NOT EXISTS ix_chunks_paper_paragraph ON chunks(paper_id, paragraph_id);

        -- Phase 6 fix: v0.2 declared paper_title + atoms_mentioned as FTS5
        -- columns under content='chunks', but those columns don't exist on
        -- the chunks table — any structural query against chunks_fts
        -- (e.g. SELECT COUNT(*)) errored with "no such column: T.paper_title".
        -- Drop the phantom columns; the paper title is joined at query time
        -- in server/db.py:query_chunks, which is the only consumer.
        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts
            USING fts5(text,
                       content='chunks', content_rowid='chunk_id',
                       tokenize='porter unicode61');

        CREATE TABLE IF NOT EXISTS atoms (
            atom_id TEXT PRIMARY KEY,
            atom_uid TEXT NOT NULL,
            name TEXT,
            category TEXT,
            -- Phase 5: refinement for hyperparameter and architecture atoms
            -- (NULL for other categories). E.g. architecture/{attention,
            -- encoder, decoder, embedding, head, other}, hyperparameter/
            -- {learning_rate, batch_size, dropout, regularization, schedule,
            -- other}. Assigned by atoms/extract.py:_subcategory.
            subcategory TEXT,
            defined_by_paper_id TEXT REFERENCES papers(paper_id),
            description TEXT,
            priority REAL
        );
        CREATE INDEX IF NOT EXISTS ix_atoms_category ON atoms(category);
        CREATE INDEX IF NOT EXISTS ix_atoms_subcategory ON atoms(subcategory);
        CREATE INDEX IF NOT EXISTS ix_atoms_defined_by ON atoms(defined_by_paper_id);
        -- atom_uid is the cross-rebuild stable join key. Unique within a single
        -- artifact; collisions across rebuilds mean the canonical name + defining
        -- paper agree (which is the whole point).
        CREATE UNIQUE INDEX IF NOT EXISTS ix_atoms_uid ON atoms(atom_uid);

        CREATE VIRTUAL TABLE IF NOT EXISTS atoms_fts
            USING fts5(name, description, category,
                       content='atoms', content_rowid='rowid',
                       tokenize='porter unicode61');

        CREATE TABLE IF NOT EXISTS atom_paper_usage (
            atom_id TEXT REFERENCES atoms(atom_id),
            paper_id TEXT REFERENCES papers(paper_id),
            role TEXT,
            PRIMARY KEY(atom_id, paper_id)
        );

        CREATE TABLE IF NOT EXISTS atom_evidence (
            evidence_id TEXT PRIMARY KEY,
            atom_id TEXT REFERENCES atoms(atom_id),
            chunk_id INTEGER REFERENCES chunks(chunk_id),
            paragraph_id TEXT,
            char_start INTEGER,
            char_end INTEGER,
            verbatim_text TEXT
        );
        CREATE INDEX IF NOT EXISTS ix_atom_evidence_atom ON atom_evidence(atom_id);
        CREATE INDEX IF NOT EXISTS ix_atom_evidence_chunk ON atom_evidence(chunk_id);

        CREATE TABLE IF NOT EXISTS edges (
            edge_id TEXT PRIMARY KEY,
            from_paper_id TEXT REFERENCES papers(paper_id),
            to_paper_id TEXT REFERENCES papers(paper_id),
            best_role TEXT,
            best_confidence REAL,
            section_type TEXT,
            paragraph_id TEXT,
            classifier TEXT,
            context TEXT,
            -- Phase 1 columns; populated in Phase 4 (citation intent classifier).
            provenance_rule TEXT,
            citation_intent TEXT,
            intent_confidence REAL,
            weight REAL
        );
        CREATE INDEX IF NOT EXISTS ix_edges_from ON edges(from_paper_id);
        CREATE INDEX IF NOT EXISTS ix_edges_to ON edges(to_paper_id);
        CREATE INDEX IF NOT EXISTS ix_edges_role ON edges(best_role);
        CREATE INDEX IF NOT EXISTS ix_edges_intent ON edges(citation_intent);

        CREATE TABLE IF NOT EXISTS edge_roles (
            edge_id TEXT REFERENCES edges(edge_id),
            label TEXT,
            confidence REAL
        );
        CREATE INDEX IF NOT EXISTS ix_edge_roles_edge ON edge_roles(edge_id);

        -- Phase 1 schema, Phase 4 populates. Citation-intent multi-labels
        -- (a single citation often plays multiple roles e.g. method + result).
        CREATE TABLE IF NOT EXISTS edge_intents (
            edge_id TEXT REFERENCES edges(edge_id),
            intent_label TEXT,
            confidence REAL
        );
        CREATE INDEX IF NOT EXISTS ix_edge_intents_edge ON edge_intents(edge_id);

        CREATE TABLE IF NOT EXISTS equations (
            equation_id TEXT PRIMARY KEY,
            paper_id TEXT REFERENCES papers(paper_id),
            section_id TEXT REFERENCES sections(section_id),
            latex TEXT
        );
        CREATE INDEX IF NOT EXISTS ix_equations_paper ON equations(paper_id);

        CREATE TABLE IF NOT EXISTS communities (
            community_id INTEGER PRIMARY KEY,
            label TEXT,
            summary TEXT,
            size INTEGER
        );

        CREATE TABLE IF NOT EXISTS community_papers (
            community_id INTEGER REFERENCES communities(community_id),
            paper_id TEXT REFERENCES papers(paper_id),
            PRIMARY KEY(community_id, paper_id)
        );

        CREATE TABLE IF NOT EXISTS community_atoms (
            community_id INTEGER REFERENCES communities(community_id),
            atom_id TEXT REFERENCES atoms(atom_id),
            PRIMARY KEY(community_id, atom_id)
        );

        CREATE TABLE IF NOT EXISTS missing_details (
            md_id TEXT PRIMARY KEY,
            question TEXT,
            category TEXT,
            options_json TEXT,
            suggested_default TEXT,
            rationale TEXT
        );

        -- Phase 1 schema; Phase 8 ingests wiki/answers/ markdown into this
        -- table and embeds bodies back into chunks_vec so promoted answers
        -- survive across rebuilds AND become retrievable via query_chunks.
        CREATE TABLE IF NOT EXISTS wiki_answers (
            answer_id TEXT PRIMARY KEY,
            slug TEXT NOT NULL,
            body_md TEXT NOT NULL,
            source_atom_uids TEXT,
            created_at TEXT,
            updated_at TEXT
        );
        CREATE INDEX IF NOT EXISTS ix_wiki_answers_slug ON wiki_answers(slug);

        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        """
    )
    if vec_loaded:
        cur.executescript(
            f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS chunks_vec
                USING vec0(embedding float[{vec_dim}]);
            CREATE VIRTUAL TABLE IF NOT EXISTS atoms_vec
                USING vec0(embedding float[{vec_dim}]);
            -- Phase 7: community-summary embeddings power the "global" mode of
            -- query routing à la Microsoft GraphRAG. KNN against this table
            -- finds the top-k thematic clusters relevant to a question; we
            -- then aggregate atoms + chunks from member papers.
            CREATE VIRTUAL TABLE IF NOT EXISTS communities_vec
                USING vec0(embedding float[{vec_dim}]);
            """
        )
    conn.commit()


def _chunk_paragraphs(paragraphs: list) -> Iterable[tuple[str, str, str]]:
    """Yield (chunk_anchor_id, cleaned_text, paragraph_id) per chunk.

    Splits long paragraphs into overlapping windows. Uses text_utils for the
    actual splitting + placeholder scrubbing so quality scoring (downstream)
    sees clean text. Whether a chunk gets indexed in FTS5 is decided by the
    caller, not here.
    """
    from .text_utils import scrub_placeholders, split_with_overlap

    for p in paragraphs:
        raw = scrub_placeholders((p.text or "").strip())
        if not raw:
            continue
        parts = split_with_overlap(raw)
        if len(parts) == 1:
            yield p.id, parts[0], p.id
        else:
            for i, part in enumerate(parts):
                yield f"{p.id}-c{i}", part, p.id


def ingest_paper(conn: sqlite3.Connection, paper, *, is_target: bool, depth: int, acquired: bool, parsed_path: Optional[str] = None) -> list[int]:
    """Insert a parsed Paper IR. Returns chunk row IDs created."""
    md = paper.metadata
    acquired_via = paper.acquisition.source if paper.acquisition else None
    conn.execute(
        """
        INSERT INTO papers(paper_id, title, year, venue, authors_json, abstract,
                           rank, scholarly_influence, implementation_influence,
                           is_target, depth, acquired, acquired_via, parsed_path)
        VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, NULL, ?, ?, ?, ?, ?)
        ON CONFLICT(paper_id) DO UPDATE SET
            title=excluded.title,
            year=excluded.year,
            venue=excluded.venue,
            authors_json=excluded.authors_json,
            abstract=excluded.abstract,
            is_target=excluded.is_target,
            depth=excluded.depth,
            acquired=excluded.acquired,
            acquired_via=excluded.acquired_via,
            parsed_path=excluded.parsed_path
        """,
        (
            paper.paper_id,
            md.title,
            md.year,
            md.venue,
            json.dumps([a.name for a in md.authors]),
            md.abstract,
            int(is_target),
            depth,
            int(acquired),
            acquired_via,
            parsed_path,
        ),
    )

    from .text_utils import classify_chunk_kind

    chunk_ids: list[int] = []
    next_ord = 0
    for ord_, sec in enumerate(paper.sections):
        conn.execute(
            "INSERT OR REPLACE INTO sections(section_id, paper_id, title, section_type, ord) VALUES (?,?,?,?,?)",
            (f"{paper.paper_id}::{sec.id}", paper.paper_id, sec.title, sec.section_type, ord_),
        )
        for cord, (chunk_marker, chunk_text, anchor) in enumerate(_chunk_paragraphs(sec.paragraphs)):
            kind, quality = classify_chunk_kind(sec.section_type, sec.title, chunk_text)
            cur = conn.execute(
                """INSERT INTO chunks(paper_id, section_id, paragraph_id, ord, text, n_tokens,
                                       is_indexed, quality, chunk_kind)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    paper.paper_id,
                    f"{paper.paper_id}::{sec.id}",
                    anchor,
                    next_ord,
                    chunk_text,
                    len(chunk_text) // 4,
                    1,  # Phase 6: always indexed
                    float(quality),
                    kind,
                ),
            )
            chunk_ids.append(cur.lastrowid)
            next_ord += 1
            # Phase 6: every chunk goes into FTS5 regardless of kind.
            conn.execute(
                "INSERT INTO chunks_fts(rowid, text) VALUES (?, ?)",
                (cur.lastrowid, chunk_text),
            )

    # Phase 6: structured items (tables, figure captions) become their own
    # chunks with chunk_kind != prose so retrieval can target them.
    # Equations are also stored in `equations` for the upcoming equation_lookup
    # MCP tool, plus surfaced as equation_block chunks for hybrid retrieval.
    for tbl in paper.tables:
        caption = (tbl.caption or "").strip()
        rows_text = ""
        if tbl.rows:
            try:
                rows_text = " | ".join(" ".join(str(c) for c in row) for row in tbl.rows[:20])
            except Exception:  # noqa: BLE001
                rows_text = ""
        text = (caption + ("  " + rows_text if rows_text else "")).strip()
        if not text:
            continue
        kind, quality = classify_chunk_kind(None, None, text, override_kind="table")
        section_id = f"{paper.paper_id}::{tbl.section_id}" if tbl.section_id else None
        cur = conn.execute(
            """INSERT INTO chunks(paper_id, section_id, paragraph_id, ord, text, n_tokens,
                                   is_indexed, quality, chunk_kind)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (paper.paper_id, section_id, tbl.id, next_ord, text, len(text) // 4, 1, float(quality), kind),
        )
        chunk_ids.append(cur.lastrowid)
        next_ord += 1
        conn.execute(
            "INSERT INTO chunks_fts(rowid, text) VALUES (?, ?)",
            (cur.lastrowid, text),
        )

    for fig in paper.figures:
        caption = (fig.caption or "").strip()
        if not caption:
            continue
        kind, quality = classify_chunk_kind(None, None, caption, override_kind="caption")
        section_id = f"{paper.paper_id}::{fig.section_id}" if fig.section_id else None
        cur = conn.execute(
            """INSERT INTO chunks(paper_id, section_id, paragraph_id, ord, text, n_tokens,
                                   is_indexed, quality, chunk_kind)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (paper.paper_id, section_id, fig.id, next_ord, caption, len(caption) // 4, 1, float(quality), kind),
        )
        chunk_ids.append(cur.lastrowid)
        next_ord += 1
        conn.execute(
            "INSERT INTO chunks_fts(rowid, text) VALUES (?, ?)",
            (cur.lastrowid, caption),
        )

    for eq in paper.equations:
        conn.execute(
            "INSERT OR REPLACE INTO equations(equation_id, paper_id, section_id, latex) VALUES (?,?,?,?)",
            (f"{paper.paper_id}::{eq.id}", paper.paper_id, f"{paper.paper_id}::{eq.section_id}" if eq.section_id else None, eq.latex),
        )
        # Also surface as a retrievable chunk so equation queries (e.g.
        # "find the Hamiltonian", "find the contrastive objective") work
        # via query_chunks without a separate tool call.
        latex = (eq.latex or "").strip()
        if not latex:
            continue
        kind, quality = classify_chunk_kind(None, None, latex, override_kind="equation_block")
        section_id = f"{paper.paper_id}::{eq.section_id}" if eq.section_id else None
        cur = conn.execute(
            """INSERT INTO chunks(paper_id, section_id, paragraph_id, ord, text, n_tokens,
                                   is_indexed, quality, chunk_kind)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (paper.paper_id, section_id, eq.id, next_ord, latex, len(latex) // 4, 1, float(quality), kind),
        )
        chunk_ids.append(cur.lastrowid)
        next_ord += 1
        conn.execute(
            "INSERT INTO chunks_fts(rowid, text) VALUES (?, ?)",
            (cur.lastrowid, latex),
        )
    return chunk_ids


def ingest_atoms_and_edges(conn: sqlite3.Connection, atoms: list, evidence: list, edges: list) -> dict:
    """Write atoms, evidence (with resolved chunk_id), and edges into the DB.

    Returns a small stats dict so the caller can record evidence-resolution
    health in build-manifest.json (Phase 1 acceptance check).
    """
    for a in atoms:
        conn.execute(
            "INSERT OR REPLACE INTO atoms(atom_id, atom_uid, name, category, subcategory, defined_by_paper_id, description, priority) VALUES (?,?,?,?,?,?,?,?)",
            (a.id, a.uid, a.name, a.category, a.subcategory, a.defined_by_paper_id, a.description, a.priority),
        )
        conn.execute(
            "INSERT INTO atoms_fts(rowid, name, description, category) VALUES ((SELECT rowid FROM atoms WHERE atom_id=?), ?, ?, ?)",
            (a.id, a.name, a.description or "", a.category),
        )
        for pid in a.used_by_paper_ids:
            conn.execute(
                "INSERT OR IGNORE INTO atom_paper_usage(atom_id, paper_id, role) VALUES (?,?,?)",
                (a.id, pid, "uses"),
            )

    ev_map = {e.id: e for e in evidence}
    ev_total = 0
    ev_resolved = 0
    for a in atoms:
        for eid in a.evidence_span_ids:
            ev = ev_map.get(eid)
            if ev is None:
                continue
            ev_total += 1
            chunk_id: Optional[int] = None
            if ev.paragraph_id:
                row = conn.execute(
                    "SELECT chunk_id FROM chunks WHERE paper_id = ? AND paragraph_id = ? ORDER BY chunk_id LIMIT 1",
                    (ev.paper_id, ev.paragraph_id),
                ).fetchone()
                if row is not None:
                    chunk_id = int(row[0])
                    ev_resolved += 1
            conn.execute(
                """
                INSERT OR REPLACE INTO atom_evidence(
                    evidence_id, atom_id, chunk_id, paragraph_id, char_start, char_end, verbatim_text
                ) VALUES (?,?,?,?,?,?,?)
                """,
                (eid, a.id, chunk_id, ev.paragraph_id, ev.char_start, ev.char_end, ev.verbatim_text),
            )

    for ce in edges:
        role, conf = (ce.roles[0].label, ce.roles[0].confidence) if ce.roles else ("related_work_only", 0.0)
        # provenance_rule, citation_intent, intent_confidence, weight stay NULL
        # in Phase 1 — Phase 4's intent classifier populates them.
        conn.execute(
            """
            INSERT OR REPLACE INTO edges(edge_id, from_paper_id, to_paper_id, best_role, best_confidence,
                                          section_type, paragraph_id, classifier, context,
                                          provenance_rule, citation_intent, intent_confidence, weight)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                ce.edge.edge_id,
                ce.edge.from_paper_id,
                ce.edge.to_paper_id,
                role,
                conf,
                ce.edge.section_type,
                ce.edge.paragraph_id,
                ce.classifier,
                ce.edge.context,
                getattr(ce, "provenance_rule", None),
                getattr(ce, "citation_intent", None),
                getattr(ce, "intent_confidence", None),
                getattr(ce, "weight", None),
            ),
        )
        # store all multi-label roles
        for r in ce.roles:
            conn.execute(
                "INSERT INTO edge_roles(edge_id, label, confidence) VALUES (?,?,?)",
                (ce.edge.edge_id, r.label, r.confidence),
            )
        # Phase 4 may attach multi-intent labels.
        for it in getattr(ce, "intents", None) or []:
            conn.execute(
                "INSERT INTO edge_intents(edge_id, intent_label, confidence) VALUES (?,?,?)",
                (ce.edge.edge_id, it.get("label"), it.get("confidence")),
            )

    if ev_total:
        print(
            f"atom_evidence: {ev_resolved}/{ev_total} chunk_id resolved "
            f"({100 * ev_resolved // ev_total}%)",
            file=sys.stderr,
        )
    return {"evidence_total": ev_total, "evidence_chunk_resolved": ev_resolved}


def ingest_missing(conn: sqlite3.Connection, details: list) -> None:
    for d in details:
        conn.execute(
            "INSERT OR REPLACE INTO missing_details(md_id, question, category, options_json, suggested_default, rationale) VALUES (?,?,?,?,?,?)",
            (d.id, d.question, d.category, json.dumps(d.options), d.suggested_default, d.rationale),
        )


def ingest_scores(conn: sqlite3.Connection, scores: dict[str, dict[str, float]]) -> None:
    for pid, s in scores.items():
        conn.execute(
            "UPDATE papers SET rank=?, scholarly_influence=?, implementation_influence=? WHERE paper_id=?",
            (s.get("rank"), s.get("scholarly_influence"), s.get("implementation_influence"), pid),
        )


def write_embeddings_vec(conn: sqlite3.Connection, chunk_ids: list[int], vectors) -> None:
    """Insert chunk embeddings (numpy array N×D) into chunks_vec."""
    import struct

    cur = conn.cursor()
    for cid, vec in zip(chunk_ids, vectors):
        blob = struct.pack(f"{len(vec)}f", *[float(x) for x in vec])
        cur.execute("INSERT INTO chunks_vec(rowid, embedding) VALUES (?, ?)", (cid, blob))


def write_atom_embeddings_vec(conn: sqlite3.Connection, atom_ids: list[str], vectors) -> None:
    import struct

    cur = conn.cursor()
    cur.execute("DELETE FROM atoms_vec")
    rowid_map = {row["atom_id"]: row["rowid"] for row in cur.execute("SELECT rowid, atom_id FROM atoms")}
    for aid, vec in zip(atom_ids, vectors):
        rid = rowid_map.get(aid)
        if rid is None:
            continue
        blob = struct.pack(f"{len(vec)}f", *[float(x) for x in vec])
        cur.execute("INSERT INTO atoms_vec(rowid, embedding) VALUES (?, ?)", (rid, blob))


def write_community_embeddings_vec(conn: sqlite3.Connection, community_ids: list[int], vectors) -> None:
    """Replace the contents of communities_vec with the supplied embeddings.

    Phase 7: the rowid IS the community_id (small integers, dense). KNN
    results map back to communities via the same id with no extra join.
    """
    import struct

    cur = conn.cursor()
    cur.execute("DELETE FROM communities_vec")
    for cid, vec in zip(community_ids, vectors):
        blob = struct.pack(f"{len(vec)}f", *[float(x) for x in vec])
        cur.execute("INSERT INTO communities_vec(rowid, embedding) VALUES (?, ?)", (int(cid), blob))


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES (?,?)", (key, value))
