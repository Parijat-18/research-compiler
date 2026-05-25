---
name: implement-data
description: Implement `data` + `preprocessing` atoms — the inputs and the transformations applied before the method. ML: dataset + tokenizer/augment. Physics: measurements + filter/calibrate. Chemistry: compound set + purification. Biology: cohort + alignment/QC.
when_to_use: User mentions implementing dataset/data loader/preprocessing/normalization/calibration/QC/tokenizer/augmentation pipeline.
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
  - mcp__paper-compiler__query_chunks
  - mcp__paper-compiler__list_missing_details
  - mcp__paper-compiler__record_decision
---

# implement-data

Inputs and their transformations. Two categories share this skill because the MCP flow is identical.

## Procedure

1. **Trace dependencies.**
   ```
   trace_dependency(component="data")
   trace_dependency(component="preprocessing")
   ```

2. **Identify the canonical source.** Each `data` atom has a `defined_by_paper_id`. That paper is canonical for splits / cohort definitions / inclusion criteria / preprocessing assumed by the benchmark. Pull it: `paper_text(paper_id=<defining>, section_type="experiments")`, narrow by paragraph.

3. **Find target-paper customizations.** Custom preprocessing lives in the **target paper's** experiments section, not the defining paper's. `query_chunks(query="<data name> preprocessing normalization filtering", limit=8)` — read snippets first, pull full text only for load-bearing hits.

4. **Resolve gaps.** `list_missing_details()` — preprocessing is the highest-rate source of missing details in compiled briefs across every field. For each gap, name an explicit default in your TODO list and (if non-trivial) `record_decision(category="preprocessing", ...)`.

5. **Implement.**
   - Mirror exact order of operations — composition order matters in every domain.
   - Honor exact constants (mean, std, threshold, cutoff) from the defining paper; don't approximate.
   - For sequence/molecular/spectral data, exact tokenizer or fingerprint encoder matters; cite the chunk.
   - If the data isn't accessible (paywall, license, ethics review), stub the loader with a docstring listing the schema and a TODO.

## See also

- `references/watchouts.md` — domain-specific pitfalls (ML mean/std, physics calibration, chem tautomer state, bio reference genome).
