# implement-objective — cross-domain watch-outs

## ML objectives
- **Temperature placement.** `softmax(sim / τ)` not `softmax(sim) / τ`.
- **Negative sign.** Many losses have a leading minus that matters only when re-derived from log-likelihood — copy from the verbatim span exactly.
- **Padding / mask exclusion.** Sequence losses must exclude padded tokens. Almost never spelled out.
- **Stop-gradient on EMA target.** Load-bearing when present.

## Physics / numerical objectives
- **Sign of action / Lagrangian.** Conventions differ; verify against the cited paper.
- **Units / non-dim factors.** Reduced (LJ) vs SI conversions.
- **Boundary / initial conditions.** Often specified once, far from the equation.
- **Convergence criterion.** Wall-time vs error tolerance vs fixed iteration count.

## Chemistry yield / selectivity
- **Yield definition.** Isolated vs NMR vs HPLC; cite the chunk.
- **Internal standard.** Identity + amount affects relative-yield math.

## Biology fitness / scoring
- **Cohort balance.** Imbalanced positives/negatives change effective objective.
- **Censoring.** Survival objectives need explicit handling.

## Verification checklist

- [ ] `atom_uid` cited in code.
- [ ] Equation / step sequence matches verbatim span.
- [ ] Parameter values from a single named chunk; chunk_id in comment.
- [ ] Synthetic dry-run on 4 hand-built samples / steps returns a sensible result.
- [ ] Missing-detail TODO list at end of response.
