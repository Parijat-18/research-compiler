---
name: audit-evaluation
description: Audit `evaluation` atoms (metrics, statistical tests, convergence diagnostics) against the implementation.
when_to_use: Auto-invoked by parent audit skill when `evaluation` atoms exist.
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

# audit-evaluation

## Recipe

1. `mcp__paper-compiler__trace_dependency(component="evaluation")`.

2. For each atom:
   - Grep `evaluate`, `metric`, `score`, `accuracy`, `f1`, `convergence`, `error_bar`, or the metric's named class.
   - Pull verbatim via `mcp__paper-compiler__get_evidence`.
   - For symbolic metrics: `equation_lookup(symbol_or_keyword=...)`.
   - Compare:
     - Metric definition (top-1 vs top-5; macro vs micro; smoothed vs not).
     - Split / replicate / cohort identity.
     - Inference / measurement conditions (resolution, run length, sample size).

3. **Score:** `DIVERGENT` if the code uses a different averaging / split / condition.

## Output

Append to `audit-report.md` under `### evaluation`.
