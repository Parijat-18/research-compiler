---
name: use-research-context
description: Use when implementing, porting, reproducing, modifying, extending, or debugging code from a research paper that has been compiled into `research/` by paper-compiler. Trigger phrases — "implement this paper", "port the architecture from X", "reproduce the loss / training / eval", "match the baseline", "fix mismatch with the paper", "add this baseline". Consults the compiled brief + Graph RAG DB + wiki before generating code, follows the per-component playbooks in `references/`, and cites evidence inline.
when_to_use: Activates when the repo contains `research/research.md` and the user is doing implementation work originating from a paper. If only one is true, suggest /paper-compiler:build-research-context.
paths:
  - research/research.md
  - research/research.db
  - research/wiki/**/*.md
allowed-tools:
  - Read
  - Glob
  - mcp__paper-compiler__paper_summary
  - mcp__paper-compiler__trace_dependency
  - mcp__paper-compiler__find_atom
  - mcp__paper-compiler__get_evidence
  - mcp__paper-compiler__list_missing_details
  - mcp__paper-compiler__equation_lookup
  - mcp__paper-compiler__compare_methods
  - mcp__paper-compiler__citation_neighbors
  - mcp__paper-compiler__graph_stats
  - mcp__paper-compiler__query_chunks
  - mcp__paper-compiler__paper_text
  - mcp__paper-compiler__community_summary
  - mcp__paper-compiler__list_communities
  - mcp__paper-compiler__neighborhood_subgraph
  - mcp__paper-compiler__shortest_path
  - mcp__paper-compiler__graph_sql
  - mcp__paper-compiler__schema_doc
---

# use-research-context

Implementation work that comes from a compiled paper. Cite every non-obvious
choice; never invent paper-specific details from memory.

## Procedure

1. **Read** `research/research.md`.
2. **Pick the playbook** that matches the implementation task and follow it:
   - Architecture component (encoder / decoder / block / attention) →
     `references/implementing-architecture.md`.
   - Loss / objective → `references/implementing-loss.md`.
   - Dataset / preprocessing / data pipeline →
     `references/implementing-dataset.md`.
   - Optimizer / scheduler / training trick → see the loss playbook
     (same MCP pattern; different atom category).
   - Evaluation protocol / metric → `references/implementing-eval.md`.
   - Baseline → `references/implementing-baseline.md`.
   - The code disagrees with the paper / something is missing →
     `references/debugging-mismatch.md`.
3. **Token discipline.** Default to snippet responses (`query_chunks` returns
   240-char snippets unless you pass `full=True`). Only ask for full text after
   you know which chunk_ids matter.
4. **Cite.** In code comments: `# per atom-013 — research/wiki/atoms/atom-013.md`.
5. **Surface assumptions.** When `list_missing_details()` lists the detail
   you need, make a visible choice and add a TODO at the end of your response.

## Rules

- The compiled DB + wiki replace web search for any paper-specific fact. Do
  not search the web for details that should be in the corpus.
- Trust the brief and DB over the raw PDF.
- Do not paraphrase `research.md` back to the user — it's already in context.
- Never hand-edit `research/research.md`, `research.db`, or generated wiki
  articles. Use the CLI / skills.

## See also

- `research/SCHEMA.md` — DB tables and columns (read once per session if you
  plan to use `graph_sql`).
- `research/wiki/SCHEMA.md` — article shapes.
- `/paper-compiler:wiki-query` for open-ended questions about the corpus.
- `/paper-compiler:audit-against-research` after you finish implementing.
