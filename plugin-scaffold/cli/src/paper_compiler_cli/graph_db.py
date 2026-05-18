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

SCHEMA_VERSION = "1.0"

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
            parsed_path TEXT
        );

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
            is_indexed INTEGER DEFAULT 1,
            quality REAL DEFAULT 1.0
        );
        CREATE INDEX IF NOT EXISTS ix_chunks_paper ON chunks(paper_id);
        CREATE INDEX IF NOT EXISTS ix_chunks_section ON chunks(section_id);
        CREATE INDEX IF NOT EXISTS ix_chunks_indexed ON chunks(is_indexed);

        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts
            USING fts5(text, paper_title, atoms_mentioned,
                       content='chunks', content_rowid='chunk_id',
                       tokenize='porter unicode61');

        CREATE TABLE IF NOT EXISTS atoms (
            atom_id TEXT PRIMARY KEY,
            name TEXT,
            category TEXT,
            defined_by_paper_id TEXT REFERENCES papers(paper_id),
            description TEXT,
            priority REAL
        );
        CREATE INDEX IF NOT EXISTS ix_atoms_category ON atoms(category);
        CREATE INDEX IF NOT EXISTS ix_atoms_defined_by ON atoms(defined_by_paper_id);

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
            verbatim_text TEXT
        );
        CREATE INDEX IF NOT EXISTS ix_atom_evidence_atom ON atom_evidence(atom_id);

        CREATE TABLE IF NOT EXISTS edges (
            edge_id TEXT PRIMARY KEY,
            from_paper_id TEXT REFERENCES papers(paper_id),
            to_paper_id TEXT REFERENCES papers(paper_id),
            best_role TEXT,
            best_confidence REAL,
            section_type TEXT,
            paragraph_id TEXT,
            classifier TEXT,
            context TEXT
        );
        CREATE INDEX IF NOT EXISTS ix_edges_from ON edges(from_paper_id);
        CREATE INDEX IF NOT EXISTS ix_edges_to ON edges(to_paper_id);
        CREATE INDEX IF NOT EXISTS ix_edges_role ON edges(best_role);

        CREATE TABLE IF NOT EXISTS edge_roles (
            edge_id TEXT REFERENCES edges(edge_id),
            label TEXT,
            confidence REAL
        );
        CREATE INDEX IF NOT EXISTS ix_edge_roles_edge ON edge_roles(edge_id);

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
    conn.execute(
        """
        INSERT INTO papers(paper_id, title, year, venue, authors_json, abstract,
                           rank, scholarly_influence, implementation_influence,
                           is_target, depth, acquired, parsed_path)
        VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, NULL, ?, ?, ?, ?)
        ON CONFLICT(paper_id) DO UPDATE SET
            title=excluded.title,
            year=excluded.year,
            venue=excluded.venue,
            authors_json=excluded.authors_json,
            abstract=excluded.abstract,
            is_target=excluded.is_target,
            depth=excluded.depth,
            acquired=excluded.acquired,
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
            parsed_path,
        ),
    )

    from .text_utils import is_indexable

    chunk_ids: list[int] = []
    for ord_, sec in enumerate(paper.sections):
        conn.execute(
            "INSERT OR REPLACE INTO sections(section_id, paper_id, title, section_type, ord) VALUES (?,?,?,?,?)",
            (f"{paper.paper_id}::{sec.id}", paper.paper_id, sec.title, sec.section_type, ord_),
        )
        for cord, (chunk_marker, chunk_text, anchor) in enumerate(_chunk_paragraphs(sec.paragraphs)):
            indexed, quality = is_indexable(sec.section_type, sec.title, chunk_text)
            cur = conn.execute(
                """INSERT INTO chunks(paper_id, section_id, paragraph_id, ord, text, n_tokens, is_indexed, quality)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    paper.paper_id,
                    f"{paper.paper_id}::{sec.id}",
                    anchor,
                    cord,
                    chunk_text,
                    len(chunk_text) // 4,
                    int(indexed),
                    float(quality),
                ),
            )
            chunk_ids.append(cur.lastrowid)
            if indexed:
                conn.execute(
                    "INSERT INTO chunks_fts(rowid, text, paper_title, atoms_mentioned) VALUES (?, ?, ?, ?)",
                    (cur.lastrowid, chunk_text, md.title or "", ""),
                )

    for eq in paper.equations:
        conn.execute(
            "INSERT OR REPLACE INTO equations(equation_id, paper_id, section_id, latex) VALUES (?,?,?,?)",
            (f"{paper.paper_id}::{eq.id}", paper.paper_id, f"{paper.paper_id}::{eq.section_id}" if eq.section_id else None, eq.latex),
        )
    return chunk_ids


def ingest_atoms_and_edges(conn: sqlite3.Connection, atoms: list, evidence: list, edges: list) -> None:
    for a in atoms:
        conn.execute(
            "INSERT OR REPLACE INTO atoms(atom_id, name, category, defined_by_paper_id, description, priority) VALUES (?,?,?,?,?,?)",
            (a.id, a.name, a.category, a.defined_by_paper_id, a.description, a.priority),
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
    for a in atoms:
        for eid in a.evidence_span_ids:
            ev = ev_map.get(eid)
            if ev is None:
                continue
            conn.execute(
                "INSERT OR REPLACE INTO atom_evidence(evidence_id, atom_id, chunk_id, verbatim_text) VALUES (?,?,?,?)",
                (eid, a.id, None, ev.verbatim_text),
            )

    for ce in edges:
        role, conf = (ce.roles[0].label, ce.roles[0].confidence) if ce.roles else ("related_work_only", 0.0)
        conn.execute(
            """
            INSERT OR REPLACE INTO edges(edge_id, from_paper_id, to_paper_id, best_role, best_confidence,
                                          section_type, paragraph_id, classifier, context)
            VALUES (?,?,?,?,?,?,?,?,?)
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
            ),
        )
        # store all multi-label roles
        for r in ce.roles:
            conn.execute(
                "INSERT INTO edge_roles(edge_id, label, confidence) VALUES (?,?,?)",
                (ce.edge.edge_id, r.label, r.confidence),
            )


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


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES (?,?)", (key, value))
