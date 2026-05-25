# Playbook — implementing an `evaluation` atom

Covers metrics, benchmarks, statistical tests — anything that decides
whether the method works. Domain-neutral by construction:
- ML: accuracy, F1, BLEU, perplexity, ROC-AUC.
- Physics: convergence diagnostic, energy conservation, χ² of fit.
- Chemistry: reaction yield, NMR / MS verification, selectivity.
- Biology: cross-validation accuracy, AUC, log-rank.

## 1. Pull eval atoms

```
trace_dependency(component="evaluation")
```

Each atom names a metric / diagnostic / test. The
`defined_by_paper_id` is the canonical source.

## 2. Pin definitions

Different papers define ostensibly-same metrics differently (top-1 vs
top-5, macro vs micro, smoothed vs not; sample vs ensemble averages;
two-tailed vs one-tailed). Get the verbatim:

```
get_evidence(atom_id="atom-NNN")
paper_text(paper_id="<defining_paper_id>", section_type="experiments")
```

For non-trivial metrics, also pull the math:

```
equation_lookup(symbol_or_keyword="<metric symbol>")
```

## 3. Identify protocol nuances

These almost never live in the metric atom — they're in the evaluation
protocol paragraph:

- Test split definition. Often `val` ≠ `test` and the paper means one.
- Conditions applied at evaluation (resolution, run length, sample size).
- Number of inference / measurement passes.
- Statistical significance procedure (paired t-test, bootstrap CI,
  permutation test).

Search:

```
query_chunks(query="<metric name> evaluation protocol split inference",
             limit=8)
```

## 4. Cross-paper baselines

If the user is comparing against published numbers, those numbers come
from the cited baseline papers, not the target. Walk:

```
citation_neighbors(paper_id="<target>", role="evaluation_dependency")
```

Each neighbor's `paper_text` tells you what scoring conditions produced
their published number.

## 5. Implement

- Reuse a known library when the metric is standard (`torchmetrics`,
  `evaluate`, `scikit-learn.metrics`, `statsmodels`, `MDAnalysis`).
  Cite the chunk where the paper names it.
- Run on one sample and one mini-batch (or one short trajectory)
  before scaling. Pad / mask / unit correctness is the most common
  eval bug across all domains.
- Print metric definition once at startup so logs are
  self-documenting.

## Watch-out list (cross-domain)

ML metrics:
- **Top-1 vs top-5 accuracy.**
- **BLEU smoothing.** SacreBLEU defaults ≠ original BLEU.
- **F1 averaging.** macro / micro / weighted differ.
- **Eval batch shuffling.** Should be off.
- **Float dtype.** fp32-eval-of-bf16-model changes the third decimal.

Physics diagnostics:
- **Block averaging vs running mean.** Affects error bars on long
  trajectories.
- **Equilibration cutoff.** Discard the first N steps; cite the chunk.
- **Energy conservation tolerance.** Often a load-bearing parameter.

Chemistry / wet-lab:
- **Yield definition.** Isolated vs NMR vs HPLC; cite the chunk.
- **Internal standard.** Identity + amount affects relative-yield math.

Biology / stats:
- **Multiple-testing correction.** Bonferroni vs FDR; not interchangeable.
- **Effect size vs p-value.** The paper usually wants both; if only one
  is reported, flag it.

## Verification checklist

- [ ] `atom_uid` cited for each metric / diagnostic.
- [ ] Definition matches verbatim chunk.
- [ ] Eval split / condition is the one named in the experiments
      section.
- [ ] One reference comparison value reproduces within tolerance.
- [ ] Statistical test (if mentioned in the paper) implemented.
