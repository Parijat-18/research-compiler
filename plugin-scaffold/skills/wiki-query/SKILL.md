---
name: wiki-query
description: Use when the user asks an open-ended question about the compiled paper or its citation neighborhood — "what's X?", "how does X relate to Y?", "why did the authors choose Z?". Answers from the compiled wiki + sqlite Graph RAG DB, with inline citations to atom_ids, paper_ids, and chunk_ids. Promotes high-value answers to `research/wiki/answers/<slug>.md` so they're reusable in future sessions. Trigger phrases: "ask the wiki", "wiki query", "what does the corpus say", "search the research".
paths:
  - research/research.db
  - research/wiki/**/*.md
allowed-tools:
  - Read
  - Write
  - mcp__paper-compiler__query_chunks
  - mcp__paper-compiler__find_atom
  - mcp__paper-compiler__get_evidence
  - mcp__paper-compiler__paper_text
  - mcp__paper-compiler__neighborhood_subgraph
  - mcp__paper-compiler__shortest_path
  - mcp__paper-compiler__list_communities
  - mcp__paper-compiler__community_summary
  - mcp__paper-compiler__graph_sql
  - mcp__paper-compiler__schema_doc
---

# wiki-query — ask the compiled research wiki

You are answering one user question against a paper-compiler corpus on disk
(`research/research.db` + `research/wiki/`). The wiki is a Karpathy-style
llm-wiki: an evolving knowledge base where good answers become new pages.

## Procedure

1. **Skim the index** — `Read("research/wiki/index.md")`.
2. **Find the relevant atoms** with `find_atom(query=...)`. If the question
   spans a relationship, use `neighborhood_subgraph(node_id=..., hops=2)` or
   `shortest_path(from_id, to_id)`.
3. **Pull evidence** with `query_chunks(query, limit=6)` (snippet-first by
   default). Drill into specific chunks with `query_chunks(..., full=True,
   chunk_ids=[...])` or `paper_text(paper_id, paragraph_ids=[...])` only after
   you've decided which ones you need.
4. **Synthesize** a 2–8 paragraph answer. Use the formatting in
   `wiki/SCHEMA.md::answers/`. Inline citations:
   - Atom: `[[atom-013|CEM optimizer]]`.
   - Paper: `[[paper-s2_5c5e69…|Rubinstein 1999]]`.
   - Chunk: `chunk_id=46` parenthetical.
5. **Promote** if the answer touched ≥2 atoms across ≥2 communities, or used
   ≥3 distinct chunks. See `references/promotion-rules.md`.
6. **Always append to `research/wiki/log.md`**. See `references/log-format.md`.

## Rules

- Never invent evidence. Every claim cites a chunk_id or atom_id.
- Stay grounded in the DB. If the corpus doesn't cover the question, say so
  explicitly and call `list_missing_details()` to suggest what's missing.
- Don't quote more than ~120 chars from a single chunk. Paraphrase, then cite.
- If the question is purely "how do I implement X?", hand off to
  `/paper-compiler:use-research-context` instead — that's the right skill for
  code generation.

## See also

- `references/promotion-rules.md` — when to write a new `answers/<slug>.md`.
- `references/log-format.md` — the `log.md` entry shape.
- `research/wiki/SCHEMA.md` — full article schema (read this once per session).
- `research/SCHEMA.md` — DB schema if you need `graph_sql`.
