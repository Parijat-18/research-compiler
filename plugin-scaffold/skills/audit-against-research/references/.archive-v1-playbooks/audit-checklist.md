# Audit checklist — per-category recipes

For each atom returned by `graph_stats()` / `trace_dependency()`, run
the recipe that matches `atom.category`. Output a single status
verdict: `IMPLEMENTED` / `PARTIAL` / `MISSING` / `DIVERGENT`.

The recipes are **domain-neutral**. Vocabulary in examples is ML by
default; substitute the field-appropriate term — `Grep` for a chemistry
"reaction conditions" atom looks the same as for an ML "loss" atom,
just with different keywords.

## `method` (algorithmic / structural unit)

ML: architecture / encoder / decoder / attention. Physics: numerical
scheme / integrator. Chemistry: synthesis route. Biology: protocol.

1. `Grep` for the atom's name + close synonyms.
2. Read the matching files. Compare:
   - Class / function / pipeline stage exists.
   - Signature accepts the same input quantities mentioned in evidence.
   - Internal structure matches paper depth / order / step count.
3. Verdicts:
   - All three match → `IMPLEMENTED`.
   - Structure mismatch (layer count, integrator order, step count)
     → `DIVERGENT` (cite verbatim chunk_id).
   - Top-level present but a sub-component (e.g. positional encoding,
     thermostat, purification step) absent → `PARTIAL`.
   - No grep hit → `MISSING`.

## `objective`

ML: loss / objective / regularizer. Physics: Hamiltonian / action.
Chemistry: yield target. Biology: fitness function.

1. `Grep` for `loss`, `criterion`, `objective`, `energy`, `hamiltonian`,
   `yield`, `fitness` (pick by domain).
2. Pull the function; compare against `get_evidence(atom_uid)`:
   - Reduction / averaging convention.
   - Sign and normalization.
   - Auxiliary terms (regularization, stop-gradient, internal
     standards).
3. Verdicts: same scale as `method`; `DIVERGENT` only with
   chunk-cited evidence.

## `data`

1. `Glob` for `data/`, `datasets/`, `measurements/`, `*data*.py`,
   `*loader*.py`.
2. Check the data is named explicitly + the split / cohort / sample
   set matches the paper.
3. Verdict template same as above.

## `preprocessing`

1. `Grep` `transform`, `tokenize`, `preprocess`, `normaliz`, `filter`,
   `calibrat`, `align`, `qc` (pick by domain).
2. Compare ordering and parameters with the paper's verbatim spec.
3. If the paper is silent on a parameter but `missing-details.md`
   lists it, the code must declare a default visibly (comment + named
   constant).

## `evaluation`

1. `Grep` `evaluate`, `metric`, `score`, `accuracy`, `f1`,
   `convergence`, `error_bar`, the named metric.
2. Compare with `get_evidence`:
   - Metric definition.
   - Split / replicate / cohort.
   - Inference conditions (resolution / run length / sample size).
3. `DIVERGENT` if the code uses a different averaging / split /
   condition.

## `baseline`

1. `Grep` the baseline's name; confirm a class or branch exists.
2. Verify the variant matches the comparison table in the target
   paper.
3. Verify it reuses the *same* data + eval pipeline as the main
   method.
4. `MISSING` is acceptable for v1 implementations — flag as TODO.

## `procedure`

ML: optimizer / scheduler / training trick. Physics: integrator /
thermostat / sampling. Chemistry: reaction protocol. Biology:
experimental procedure.

1. `Grep` the procedure name; grep its parameters.
2. Compare with the paper's training-details / methods chunk.
3. Common silent divergences:
   - EMA target with missing `ema_decay` (ML).
   - Thermostat coupling time (physics).
   - Reaction temperature ramp (chemistry).
   - Read-quality filter cutoff (biology).

## `parameter`

1. `Grep` the parameter name as a literal or variable.
2. Confirm the value matches the paper. Tolerance: exact match for
   integer / count values; ±5% for float parameters not otherwise
   constrained (or the paper's reported precision).

## `theory`

1. Check whether a theorem / assumption / principle is invoked
   explicitly (comment or docstring referencing the chunk).
2. Verify any preconditions cited in the paper hold in the
   implementation (e.g. positive-definite matrix, mass conservation,
   detailed balance).
3. `MISSING` is acceptable here — theory atoms often inform but don't
   require code.

## Final cross-check

`list_missing_details()` should be inspected at the end. Every open
question must be visible somewhere in the code — a comment, a named
config value, or a TODO. Anything in `missing-details.md` *and*
invisible in code goes under "Unflagged assumptions" in the report.
