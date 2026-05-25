---
name: audit-data
description: Audit `data` and `preprocessing` atoms (datasets, measurements, samples, cohorts; tokenizers, normalization, calibration, QC) against the implementation.
when_to_use: Auto-invoked by parent audit skill when `data` or `preprocessing` atoms exist.
context: fork
allowed-tools:
  - Read
  - Grep
  - Glob
  - mcp__paper-compiler__find_atom
  - mcp__paper-compiler__get_evidence
  - mcp__paper-compiler__trace_dependency
  - mcp__paper-compiler__list_missing_details
---

# audit-data

## Recipe

1. `mcp__paper-compiler__trace_dependency(component="data")` and `component="preprocessing"`.

2. For each atom:
   - `Glob` `data/`, `datasets/`, `measurements/`, `*data*.py`, `*loader*.py`.
   - Grep `transform`, `tokenize`, `preprocess`, `normaliz`, `filter`, `calibrat`, `align`, `qc` (pick by domain).
   - Check:
     - Data named explicitly + split / cohort / sample set matches paper.
     - Preprocessing order of operations matches verbatim spec.
     - Numerical constants (mean, std, threshold, cutoff) match exactly.

3. **Cross-check** `mcp__paper-compiler__list_missing_details()` — preprocessing is the top source of missing details. Every open question must be visible in code (comment + named constant) or get a TODO.

4. **Score:** `PARTIAL` is common — flag missing augmentations / calibrations / QC steps.

## Output

Append to `audit-report.md` under `### data` and `### preprocessing`.
