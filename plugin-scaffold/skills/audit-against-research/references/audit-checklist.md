# Audit checklist — per-category recipes

For each atom returned by `graph_stats()` / `trace_dependency()`, run the
recipe that matches `atom.category`. Output a single status verdict:
`IMPLEMENTED` / `PARTIAL` / `MISSING` / `DIVERGENT`.

## architecture

1. `Grep` for the atom's name + close synonyms (e.g. atom "Vision Transformer
   Encoder" → grep `ViT`, `VisionTransformer`, `encoder`).
2. Read the matching files. Compare:
   - Module class exists.
   - Forward signature accepts the same input shape mentioned in evidence.
   - Internal block stack matches paper depth / dim.
3. Verdicts:
   - All three match → `IMPLEMENTED`.
   - Class exists but layer count or dim mismatches → `DIVERGENT` (cite
     verbatim chunk_id).
   - Class exists, shapes match, but a sub-component (e.g. positional
     encoding) is absent → `PARTIAL`.
   - No grep hit → `MISSING`.

## loss

1. `Grep` for `loss`, `criterion`, `objective`.
2. Pull the function; compare against `get_evidence(atom_id)`:
   - Reduction (mean/sum), normalization, sign.
   - Temperature placement.
   - Stop-gradient on target if mentioned in the chunk.
3. Verdicts: same as architecture; `DIVERGENT` only with chunk-cited evidence.

## dataset

1. `Glob` for `data/`, `datasets/`, `*data*.py`.
2. Check the dataset is named explicitly + the split matches the paper.
3. Preprocessing pipeline:
   - Same order of transforms.
   - Mean/std match the dataset paper's values.
4. `PARTIAL` is common here — flag missing augmentations.

## preprocessing

1. Grep `transform`, `tokenize`, `preprocess`.
2. Compare ordering and parameters with the paper's verbatim spec.
3. If the paper is silent on a param but `missing-details.md` lists it, the
   code must declare a default visibly (comment + named constant).

## evaluation

1. Grep `evaluate`, `metric`, `accuracy`, `f1`, the metric's named class.
2. Compare with `get_evidence`:
   - Metric definition (top-1/5, micro/macro, smoothed).
   - Split (val vs test).
   - Inference conditions (resolution, num passes).
3. `DIVERGENT` if the code uses a different averaging / different split.

## baseline

1. Grep the baseline's name; confirm there's a class or branch for it.
2. Verify the variant matches the comparison table in the target paper.
3. Verify it reuses the *same* data + eval pipeline as the main method.
4. `MISSING` is acceptable for v1 implementations — flag as TODO.

## optimizer / training_trick

1. Grep `Adam`, `SGD`, the optimizer name; grep `lr`, `schedule`,
   `warmup`, `ema`.
2. Compare hyperparameters with the paper's training-details chunk.
3. EMA: a missing `ema_decay` is a common silent divergence; the verbatim
   says it explicitly.

## hyperparameter

1. Grep the hyperparameter name as a literal or variable.
2. Confirm the value matches the paper. Tolerance: exact match required for
   integer values; ±5% acceptable for float hyperparameters not otherwise
   constrained.

## Final cross-check

`list_missing_details()` should be inspected at the end. Every open question
must be visible somewhere in the code — a comment, a named config value, or
a TODO. Anything in `missing-details.md` *and* invisible in code goes under
"Unflagged assumptions" in the report.
