---
name: audit-objective
description: Audit `objective` atoms (loss / Hamiltonian / yield target / fitness function) against the implementation.
when_to_use: Auto-invoked by parent audit skill when `objective` atoms exist.
context: fork
allowed-tools:
  - Read
  - Grep
  - Glob
  - mcp__paper-compiler__find_atom
  - mcp__paper-compiler__get_evidence
  - mcp__paper-compiler__trace_dependency
  - mcp__paper-compiler__equation_lookup
---

# audit-objective

## Recipe

1. `mcp__paper-compiler__trace_dependency(component="objective")`.

2. For each atom:
   - Domain-neutral grep targets: `loss`, `criterion`, `objective`, `energy`, `hamiltonian`, `yield`, `fitness` (pick by domain).
   - Pull the function from code.
   - `mcp__paper-compiler__get_evidence(atom_id=...)`; for symbolic forms also `equation_lookup(symbol_or_keyword=...)`.
   - Compare:
     - Reduction / averaging convention.
     - Sign and normalization.
     - Auxiliary terms (regularization, stop-gradient, internal standards).
     - Padding / mask exclusion where applicable.

3. **Score:** same scale as `audit-method`; `DIVERGENT` only with chunk-cited evidence.

## Output

Append to `audit-report.md` under `### objective`.
