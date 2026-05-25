---
name: audit-baseline
description: Audit `baseline` atoms (published comparison methods) against the implementation.
when_to_use: Auto-invoked by parent audit skill when `baseline` atoms exist.
context: fork
allowed-tools:
  - Read
  - Grep
  - Glob
  - mcp__paper-compiler__find_atom
  - mcp__paper-compiler__get_evidence
  - mcp__paper-compiler__citation_neighbors
---

# audit-baseline

## Recipe

1. `mcp__paper-compiler__citation_neighbors(paper_id=<target>, role="baseline_dependency")`.

2. For each baseline:
   - Grep the baseline's name; confirm there's a class / branch / call site.
   - Verify the variant matches the comparison table in the target paper.
   - Verify it re-uses the *same* data + eval pipeline as the main method.

3. **Score:**
   - `MISSING` is acceptable for v1 implementations — flag as TODO rather than blocker.
   - `DIVERGENT` if the baseline is implemented with a different data/eval pipeline than the target's.

## Output

Append to `audit-report.md` under `### baseline`.
