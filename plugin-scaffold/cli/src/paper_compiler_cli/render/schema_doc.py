"""Emit research/SCHEMA.md — the schema reference Claude reads to learn the DB.

Kept in sync with the actual CREATE TABLE statements in graph_db.py. If you
change the DB schema, update this file.
"""

from __future__ import annotations

from pathlib import Path

SCHEMA_MD = """# `research/research.db` — schema reference

Single SQLite file with sqlite-vec (`chunks_vec`, `atoms_vec`) and FTS5
(`chunks_fts`, `atoms_fts`) extensions. Use the MCP tools for normal queries
(`mcp__paper-compiler__*`); read this file if you want to write raw SQL or
understand the foreign-key graph.

## Conventions

- Every `paper_id` looks like `s2:<40-hex>` and refers to a row in `papers`.
- `target_paper_id` is in the `meta` table: `SELECT value FROM meta WHERE key='target_paper_id'`.
- The graph is **bidirectional through `edges`**: an edge from A to B doesn't
  imply a row from B to A. Query both directions in `paper_id` traversals.
- Atoms are the **unit of implementation**. Use them whenever Claude is about
  to write code that involves a specific component of the paper — a method,
  objective, dataset, procedure, parameter, etc. The plugin is domain-neutral:
  the same categories work for ML, physics, chemistry, biology, etc.

## Core tables

### `papers`
| col | type | notes |
|---|---|---|
| paper_id | TEXT PK | `s2:<hex>` |
| title | TEXT | |
| year | INTEGER | |
| venue | TEXT | |
| authors_json | TEXT | JSON list of author names |
| abstract | TEXT | nullable |
| rank | REAL | `0.7 * impl_inf + 0.3 * sch_inf` |
| scholarly_influence | REAL | from S2 + recency |
| implementation_influence | REAL | per-edge confidence + atoms defined |
| is_target | INTEGER | 1 for the paper that was compiled |
| depth | INTEGER | 0 target, 1 cited, 2 grand-cited |
| acquired | INTEGER | 1 if full text was fetched + parsed |
| parsed_path | TEXT | cache path to parsed IR JSON |

### `sections`
| col | type | notes |
|---|---|---|
| section_id | TEXT PK | `<paper_id>::sec-<n>` |
| paper_id | FK | |
| title | TEXT | |
| section_type | TEXT | abstract\\|introduction\\|related_work\\|method\\|experiments\\|results\\|discussion\\|conclusion\\|appendix\\|other |
| ord | INTEGER | order in paper |

### `chunks`
Paragraph-sized retrieval units across all acquired papers (target + neighborhood).
| col | type | notes |
|---|---|---|
| chunk_id | INTEGER PK | row id used by `chunks_fts` and `chunks_vec` |
| paper_id | FK | |
| section_id | FK | nullable |
| paragraph_id | TEXT | source paragraph anchor |
| ord | INTEGER | order within section |
| text | TEXT | raw paragraph text |
| n_tokens | INTEGER | rough estimate |
| is_indexed | INTEGER | 1 if present in `chunks_fts` + `chunks_vec`; 0 for tables, captions, low-prose noise |
| quality | REAL | 0..1 prose-quality score; used downstream as a soft rerank prior |

#### `chunks_fts` (FTS5)
Virtual table over `chunks.text + paper_title + atoms_mentioned`. Query with `MATCH`:
```sql
SELECT chunks.chunk_id, chunks.paper_id, chunks.text
FROM chunks_fts JOIN chunks ON chunks.chunk_id = chunks_fts.rowid
WHERE chunks_fts MATCH 'objective AND function'  -- or any field-appropriate keywords
ORDER BY bm25(chunks_fts) LIMIT 10;
```

#### `chunks_vec` (sqlite-vec)
384-dim float embeddings keyed by `chunk_id`. KNN search **requires** an explicit `k = ?` constraint per sqlite-vec semantics:
```sql
SELECT chunks.chunk_id, chunks.text, distance
FROM chunks_vec
JOIN chunks ON chunks.chunk_id = chunks_vec.rowid
WHERE embedding MATCH ? AND k = 8
ORDER BY distance;
```

### `atoms`
| col | type | notes |
|---|---|---|
| atom_id | TEXT PK | `atom-<NNN>` — sequential, **changes between compiles** |
| atom_uid | TEXT UNIQUE | content-stable id (`sha1(category, canonical_name, defining_paper_id)[:16]`) — **survives rebuilds**; use this for cross-compile references |
| name | TEXT | |
| category | TEXT | method\\|objective\\|data\\|preprocessing\\|evaluation\\|baseline\\|procedure\\|parameter\\|theory (domain-neutral; ML *architecture* → method, ML *loss* → objective, ML *optimizer* → procedure, ML *hyperparameter* → parameter, etc.) |
| defined_by_paper_id | FK | usually the target; sometimes a cited paper |
| description | TEXT | one-sentence summary |
| priority | REAL | implementation priority 0..1 |

### `atoms_fts` and `atoms_vec`
Same shape as `chunks_*` but over atom name + description.

### `atom_paper_usage`
Many-to-many: which papers use which atom. `role` is `uses` (default) or `defines`.

### `atom_evidence`
| col | type | notes |
|---|---|---|
| evidence_id | TEXT PK | `ev-<NNN>` |
| atom_id | FK | |
| chunk_id | FK | source chunk in `chunks` — **populated** in v2 (was always NULL in v1) |
| paragraph_id | TEXT | source paragraph anchor (same value as `chunks.paragraph_id`) |
| char_start, char_end | INTEGER | offsets within the verbatim span |
| verbatim_text | TEXT | the exact quoted text |

### `edges`
Citation edges between papers, classified by implementation role.
| col | type | notes |
|---|---|---|
| edge_id | TEXT PK | `<from>::<to>::<occ>` |
| from_paper_id | FK | |
| to_paper_id | FK | |
| best_role | TEXT | from PRD §12 label set |
| best_confidence | REAL | 0..1 |
| section_type | TEXT | section in `from_paper` where the citation appeared |
| paragraph_id | TEXT | |
| classifier | TEXT | `heuristic` or `llm` |
| context | TEXT | surrounding paragraph text |
| provenance_rule | TEXT | which rule created this edge (`s2_cited_by`, `bib_resolve`, `inline_cite_match`, `atom_coref`, `llm_judgment`) — populated by Phase 4 |
| citation_intent | TEXT | `background`, `method`, `result`, `extends`, `contrasts`, `mention` — from SciCite-style intent classifier (Phase 4) |
| intent_confidence | REAL | classifier confidence for `citation_intent` |
| weight | REAL | combined edge weight: `best_confidence × intent_weight × role_weight` (Phase 4) |

### `edge_roles`
Multi-label: each `edge_id` may have multiple `(label, confidence)` rows.

### `edge_intents`
Multi-label citation intents (a single citation often plays multiple roles, e.g. method + result). Populated by Phase 4.

### `wiki_answers`
Survives across rebuilds. Phase 8 ingests `research/wiki/answers/*.md` into this table and embeds the body back into `chunks_vec` (with `paper_id=NULL`, `chunk_kind="answer"`) so promoted answers are retrievable via `query_chunks`.

### `equations`
| equation_id | paper_id | section_id | latex |

### `communities`
| community_id | label | summary | size |
LLM-summarized clusters from greedy modularity over the paper graph.

`community_papers` and `community_atoms` are join tables.

### `missing_details`
Open implementation questions the compiler couldn't resolve.

### `meta`
Key-value store. Useful keys: `target_paper_id`, `schema_version` (`"2.0"` in this artifact), `compiled_at`.

## Common query patterns

**1. Get every chunk that mentions a concept.**
```sql
SELECT c.paper_id, p.title, c.text
FROM chunks_fts
JOIN chunks c ON c.chunk_id = chunks_fts.rowid
JOIN papers p ON p.paper_id = c.paper_id
WHERE chunks_fts MATCH 'flash attention'
ORDER BY bm25(chunks_fts) LIMIT 10;
```

**2. Trace the chain for an implementation component.**
```sql
SELECT a.atom_id, a.name, a.category, p.title AS defining_paper
FROM atoms a
JOIN papers p ON p.paper_id = a.defined_by_paper_id
WHERE a.category = 'objective'   -- or 'method' / 'data' / 'procedure' / ...
ORDER BY a.priority DESC;
```

**3. Walk citation neighborhood by role.**
```sql
SELECT e.to_paper_id, p.title, e.best_role, e.best_confidence
FROM edges e JOIN papers p ON p.paper_id = e.to_paper_id
WHERE e.from_paper_id = (SELECT value FROM meta WHERE key = 'target_paper_id')
  AND e.best_role = 'method_dependency'  -- or 'objective_dependency' / ...
ORDER BY e.best_confidence DESC;
```

**4. Find papers in the same community as a given paper.**
```sql
SELECT cp.paper_id, p.title FROM community_papers cp
JOIN papers p ON p.paper_id = cp.paper_id
WHERE cp.community_id = (
  SELECT community_id FROM community_papers WHERE paper_id = ?
);
```

**5. All evidence for an atom (verbatim text).**
```sql
SELECT ae.verbatim_text FROM atom_evidence ae WHERE ae.atom_id = ?;
```

## How to use this with Claude Code

You do **not** need to write SQL yourself in normal use. The MCP server exposes:

- `mcp__paper-compiler__query_chunks(query, limit, full=False, max_per_paper=2)` — hybrid BM25 + vector over `chunks_fts` / `chunks_vec`. Snippet-first by default; pass `full=True` once you've narrowed the chunk_ids. Diversified: at most `max_per_paper` chunks from any single paper.
- `mcp__paper-compiler__find_atom(query, limit)` — same hybrid search over atoms.
- `mcp__paper-compiler__paper_text(paper_id, section_type?, paragraph_ids?, chunk_ids?, full=False)` — snippet-first paragraph index per paper.
- `mcp__paper-compiler__neighborhood_subgraph(node_id, hops=2, role_filter?, limit=40)` — BFS-expanded labeled subgraph rooted at a paper or atom. Returns `via_atoms` bridging shared sub-clusters.
- `mcp__paper-compiler__shortest_path(from_id, to_id, max_hops=4, k=3, role_filter?)` — up to k shortest paths through the citation + atom graph.
- `mcp__paper-compiler__community_summary(community_id)` — community report + members.
- `mcp__paper-compiler__graph_sql(sql, params?)` — read-only SELECT/WITH escape hatch. Reference this file before writing custom SQL.

If `graph_sql` is unavailable in your build, all read-only queries can also be issued via `Bash(sqlite3 research/research.db "<query>")`.
"""


def write_schema_doc(path: Path) -> None:
    path.write_text(SCHEMA_MD)
