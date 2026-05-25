---
name: implement-evaluation
description: Implement an `evaluation` atom — how outputs are judged. ML: accuracy/F1/BLEU. Physics: convergence diagnostic, χ² of fit. Chemistry: yield/NMR/MS. Biology: cross-validation accuracy, AUC, log-rank.
when_to_use: User mentions implementing a metric, score, benchmark, statistical test, convergence diagnostic, or evaluation protocol.
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
  - mcp__paper-compiler__equation_lookup
  - mcp__paper-compiler__citation_neighbors
  - mcp__paper-compiler__record_decision
---

# implement-evaluation

How outputs are judged. Domain-neutral by construction.

## Procedure

1. **Pull eval atoms.** `trace_dependency(component="evaluation")`. Each atom names a metric/diagnostic/test. The `defined_by_paper_id` is the canonical source.

2. **Pin definitions.** Different papers define ostensibly-same metrics differently (top-1 vs top-5, macro vs micro, smoothed vs not; sample vs ensemble; two-tailed vs one-tailed).
   - `get_evidence(atom_id=...)`
   - `paper_text(paper_id=<defining>, section_type="experiments")`
   - For symbolic metrics: `equation_lookup(symbol_or_keyword=...)`

3. **Identify protocol nuances.** These live in the evaluation-protocol paragraph, not the metric atom:
   - Test split / replicate / cohort definition.
   - Conditions applied at evaluation (resolution, run length, sample size).
   - Number of inference / measurement passes.
   - Statistical significance procedure.
   - `query_chunks(query="<metric name> evaluation protocol split inference", limit=8)`.

4. **Cross-paper baselines.** If comparing against published numbers, walk to the baseline papers: `citation_neighbors(paper_id=<target>, role="evaluation_dependency")`. Each neighbor's `paper_text` tells you the scoring conditions they used.

5. **Implement.** Reuse a known library when the metric is standard (`torchmetrics`, `evaluate`, `sklearn.metrics`, `statsmodels`, `MDAnalysis`). Cite the chunk where the paper names it. Print metric definition once at startup so logs are self-documenting.

## See also

- `references/watchouts.md` — cross-domain pitfalls (ML averaging, physics block averaging, chem yield definition, bio multiple-testing).
