---
name: implement-baseline
description: Implement a `baseline` atom — a published method/system/procedure the target paper compares against. ML baselines, physics reference simulations, chemistry control reactions, biology comparator protocols.
when_to_use: User asks to add a baseline, implement a comparison method, or reproduce a prior-method number from the paper's tables.
context: fork
allowed-tools:
  - Read
  - Glob
  - Edit
  - Write
  - mcp__paper-compiler__get_paper_context
  - mcp__paper-compiler__paper_summary
  - mcp__paper-compiler__find_atom
  - mcp__paper-compiler__get_evidence
  - mcp__paper-compiler__paper_text
  - mcp__paper-compiler__query_chunks
  - mcp__paper-compiler__citation_neighbors
  - mcp__paper-compiler__record_decision
---

# implement-baseline

A baseline is a published method the target paper compares against. Use when the user says "add baseline X" or "implement the comparison method".

## Procedure

1. **Pull baseline edges.** `citation_neighbors(paper_id=<target>, role="baseline_dependency")` returns each baseline as `paper_id + best_confidence + section_type + context_excerpt`. The excerpt tells you which results table / figure cited it.

2. **Pick the minimum spec to reproduce.** Don't reimplement whole. The target paper used the baseline under specific conditions (one dataset / one run length / one budget). Pull only what matches:
   - `paper_summary(paper_id=<baseline>)`
   - `paper_text(paper_id=<baseline>, section_type="method")`

   If the baseline paper was acquired and parsed, its method is in the DB. If not, flag the gap and fall back to `query_chunks(query="<baseline name> setup parameters", limit=6)`.

3. **Check for official artifacts.** `find_atom(query="<baseline> implementation reference")` — atoms often point to a defining paper that names an official repo, simulation engine, or measurement instrument. Prefer those over re-deriving from the PDF.

4. **Implement.**
   - **Drop-in API parity** with the target paper's main method — same data loader, same evaluation loop, only the method class differs.
   - Variant matters: if the baseline has small/base/large or v1/v2 parameters, implement only the variant the target paper compared against. Cite the chunk.
   - Re-use existing data and evaluation code.

## When to record a decision

If the baseline paper isn't in the corpus and you're filling in from memory or inference, that's a decision worth recording: `record_decision(category="baseline", decision="used official-looking defaults for <baseline>", why="defining paper not in research/")`.

## See also

- `references/watchouts.md` — cross-domain pitfalls (inference resolution, training budget, force-field version, comparator dataset).
