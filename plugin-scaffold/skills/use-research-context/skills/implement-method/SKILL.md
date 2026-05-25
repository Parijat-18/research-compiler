---
name: implement-method
description: Implement a `method` atom — the algorithmic/structural unit of the paper. Use when the user asks to implement an architecture (ML), numerical scheme (physics), synthesis route (chemistry), protocol (biology), or any named algorithm. Domain-neutral.
when_to_use: User mentions implementing an encoder, decoder, attention block, integrator, scheme, algorithm, synthesis route, protocol, or any structural unit named in the paper.
context: fork
allowed-tools:
  - Read
  - Glob
  - Edit
  - Write
  - mcp__paper-compiler__get_paper_context
  - mcp__paper-compiler__find_atom
  - mcp__paper-compiler__get_evidence
  - mcp__paper-compiler__trace_dependency
  - mcp__paper-compiler__paper_text
  - mcp__paper-compiler__equation_lookup
  - mcp__paper-compiler__neighborhood_subgraph
  - mcp__paper-compiler__record_decision
---

# implement-method

The algorithmic/structural unit of the paper. ML: architecture. Physics: numerical scheme. Chemistry: synthesis route. Biology: protocol. The MCP query pattern is the same across domains; only the vocabulary in the verbatim spans changes.

## Procedure

1. **Locate the atom.** `find_atom(query="<component>", limit=5)` for a named entity. For "the encoder / integrator / synthesis route" class queries, use `trace_dependency(component="method")` — returns the ranked chain with defining paper ids.

2. **Pin the defining paper.** Read `atom.defined_by_paper_id`. If target paper → the atom is novel; implement against the target. If a cited paper → implement against the cited paper, not the target's paraphrase.

3. **Pull verbatim source-of-truth.** `get_evidence(atom_id=...)` returns the spans. If incomplete: `paper_text(paper_id=<defining>, section_type="method")`, then narrow to specific `paragraph_ids` with `full=True`.

4. **Check load-bearing math / steps.** `equation_lookup(symbol_or_keyword=...)` for symbolic content. For step-ordered procedures (chem/bio), grep the section text for "first / then / next" sequencing — `query_chunks(query="<method> step order", prefer_kind="prose")`.

5. **Disambiguate via the graph.** When two methods share a name (e.g. ResNet-50 with different stem, Heck coupling vs Mizoroki-Heck), `neighborhood_subgraph(node_id=atom_id, hops=2)` and use `via_atoms` to find shared papers.

6. **Implement.** Match exact shapes/quantities from verbatim spans, never from diagrams. Where the target paper customizes a method, implement the cited base then layer the delta. Comment each non-obvious choice with `# per atom_uid <hex>` (uid survives rebuilds; sequential atom_id does not).

## When to record a decision

If you make a load-bearing choice not directly stated in the paper (e.g. a default that the paper omits, a convention adopted to resolve ambiguity), call `record_decision(category="method", atom_uid=..., decision=..., why=...)`. The next session sees it via `get_decisions_since`.

## See also

- `references/watchouts.md` — cross-domain pitfalls (ML pre/post-norm, physics stencils, chem stoichiometry, bio reference genome version).
- `/paper-compiler:use-research-context debug-divergence` if your implementation disagrees with the paper.
