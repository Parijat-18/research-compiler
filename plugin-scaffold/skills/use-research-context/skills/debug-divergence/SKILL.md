---
name: debug-divergence
description: Debug a divergence between your implementation and the paper. Use when the user reports their numbers don't match, the loss is diverging, the simulation blew up, the yield is wrong, or the code disagrees with the paper.
when_to_use: User mentions "doesn't match", "diverging", "collapsing", "wrong answer", "loss exploded", "yield is wrong", or any reproduction-fidelity issue.
context: fork
allowed-tools:
  - Read
  - Grep
  - Glob
  - mcp__paper-compiler__get_paper_context
  - mcp__paper-compiler__find_atom
  - mcp__paper-compiler__get_evidence
  - mcp__paper-compiler__compare_methods
  - mcp__paper-compiler__neighborhood_subgraph
  - mcp__paper-compiler__shortest_path
  - mcp__paper-compiler__paper_text
  - mcp__paper-compiler__query_chunks
  - mcp__paper-compiler__graph_sql
  - mcp__paper-compiler__schema_doc
  - mcp__paper-compiler__get_decisions_since
  - mcp__paper-compiler__record_decision
---

# debug-divergence

Code doesn't match the paper. Work through this in order.

## Procedure

1. **Restate the mismatch precisely.** Before any tool call, pin down: which number / behavior / shape / trajectory / yield diverges, by how much, and where the user's code claims to follow the paper.

2. **Check the decision log first.** `get_decisions_since(since="<weeks-ago>")` — past decisions / gotchas / failed approaches often explain the current divergence. If a relevant entry exists, surface it immediately.

3. **Re-pull the source-of-truth chunk.** The user's claim "the paper says X" is the first thing to verify.
   - `find_atom(query="<component in question>")`
   - `get_evidence(atom_id=...)`
   - Compare verbatim text against the user's belief. Mismatches here are the most common root cause across every domain.

4. **Compare two atoms directly.** If the user mixed up two components: `compare_methods(atom_a=..., atom_b=...)`.

5. **Walk the graph.** Missing **dependency** atoms are a frequent cause.
   - `neighborhood_subgraph(node_id=<failing_atom>, hops=2)` — `via_atoms` highlights cross-paper shared components.
   - If subgraph reveals a paper defining an atom you're not using, that's a candidate fix.

6. **Walk the citation path.** Sometimes the mismatch is in something inherited two hops away (a tokenizer from a 5-year-old paper, a force-field from a 10-year-old paper): `shortest_path(from_id=<target>, to_id=<suspect>)`.

7. **Custom SQL escape hatch.** If above don't pin it down:
   - `schema_doc()` → read the schema
   - `graph_sql("SELECT ... ")` — useful: edges where heuristic and LLM disagree, atoms used by ≥3 papers, edges with `best_role='contradicts'` or `citation_intent='contrasts'`.

8. **Patch.** Smallest change that closes the gap. Cite `chunk_id` + `atom_uid` in the patch comment. **Record the resolution**: `record_decision(category=<atom-category>, atom_uid=..., decision="...", why="...")` — next session sees it.

## Rules

- The brief is not the paper. If the brief and the verbatim chunk disagree, trust the chunk.
- A failing dry-run on synthetic input often beats reading more code.
- If something genuinely isn't in the corpus, ingest the missing reference with `/paper-compiler:wiki-ingest`.

## Verification checklist

- [ ] Mismatch restated in one sentence.
- [ ] Re-pulled chunk confirms or refutes the user's claim about the paper.
- [ ] Fix cites the `atom_uid` + `chunk_id`.
- [ ] Synthetic-input dry-run passes.
- [ ] Resolution logged via `record_decision` so the next session sees it.
