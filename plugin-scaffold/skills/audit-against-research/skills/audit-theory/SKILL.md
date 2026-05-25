---
name: audit-theory
description: Audit `theory` atoms (theorems, assumptions, principles, conservation laws) against the implementation.
when_to_use: Auto-invoked by parent audit skill when `theory` atoms exist.
context: fork
allowed-tools:
  - Read
  - Grep
  - Glob
  - mcp__paper-compiler__find_atom
  - mcp__paper-compiler__get_evidence
  - mcp__paper-compiler__trace_dependency
---

# audit-theory

`theory` atoms inform without always requiring code. Audit is light-touch.

## Recipe

1. `mcp__paper-compiler__trace_dependency(component="theory")`.

2. For each atom:
   - Check whether a theorem / assumption / principle is invoked explicitly in code (comment, docstring, or assert referencing the chunk).
   - Verify any preconditions cited in the paper hold in the implementation (e.g. positive-definite matrix, mass conservation, detailed balance, energy conservation tolerance).

3. **Score:**
   - `IMPLEMENTED` — assertion / comment present and precondition checked.
   - `PARTIAL` — assertion present, precondition not actively verified.
   - `MISSING` — acceptable for theory atoms; flag as TODO rather than blocker.
   - `DIVERGENT` — code violates a stated precondition (high severity).

## Output

Append to `audit-report.md` under `### theory`.
