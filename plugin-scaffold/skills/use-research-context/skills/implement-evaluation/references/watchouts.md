# implement-evaluation — cross-domain watch-outs

## ML metrics
- **Top-1 vs top-5 accuracy.**
- **BLEU smoothing.** SacreBLEU defaults ≠ original BLEU.
- **F1 averaging.** macro / micro / weighted differ.
- **Eval batch shuffling.** Should be off.
- **Float dtype.** fp32-eval-of-bf16-model changes the third decimal.

## Physics diagnostics
- **Block averaging vs running mean.** Affects error bars on long trajectories.
- **Equilibration cutoff.** Discard first N steps; cite the chunk.
- **Energy conservation tolerance.** Often a load-bearing parameter.

## Chemistry / wet-lab
- **Yield definition.** Isolated vs NMR vs HPLC; cite the chunk.
- **Internal standard.** Identity + amount affects relative-yield math.

## Biology / stats
- **Multiple-testing correction.** Bonferroni vs FDR; not interchangeable.
- **Effect size vs p-value.** Paper usually wants both; if only one reported, flag it.

## Verification checklist

- [ ] `atom_uid` cited for each metric / diagnostic.
- [ ] Definition matches verbatim chunk.
- [ ] Eval split / condition is the one named in the experiments section.
- [ ] One reference comparison value reproduces within tolerance.
- [ ] Statistical test (if mentioned) implemented.
