# implement-data — cross-domain watch-outs

## ML datasets / preprocessing
- **Mean / std.** Different per dataset; never assume ImageNet values for non-ImageNet.
- **Crop sizes.** Train and eval often differ.
- **Tokenizer special tokens.** BOS/EOS/pad inclusion changes loss computation.
- **Augmentation magnitudes.** RandAug m=9 and m=15 are not interchangeable.
- **Sampling.** Iterable vs map-style; with/without replacement.

## Physics / experimental data
- **Units and reference frame.** Detector vs lab frame; SI vs natural units.
- **Calibration constants.** Apply per-run or globally.
- **Background subtraction window.** Affects downstream statistics.

## Chemistry data / compound sets
- **Tautomer / protonation state.** Standardize consistently.
- **Stereochemistry.** Include or strip; changes the search space.
- **Salt / fragment removal.** Often implicit in the defining paper.

## Biology / sequencing / cohort data
- **Reference genome version.** Changes coordinates downstream.
- **Read-quality filter thresholds.** Affects coverage estimates.
- **Inclusion / exclusion criteria.** Sample-size sanity check.

## Verification checklist

- [ ] `atom_uid`s cited for each data + preprocessing step.
- [ ] Tokenizer / encoder / pipeline identified by exact name + version.
- [ ] Splits / cohorts / sample counts match the defining paper.
- [ ] All gaps from `list_missing_details()` resolved with explicit defaults.
- [ ] Data stub or real loader produces one valid sample.
