# Playbook — implementing `data` / `preprocessing` atoms

These two categories cover *inputs* and *transformations on inputs*:

- `data`: the corpus / measurements / samples / sequences /
  observations the paper uses.
- `preprocessing`: how raw inputs are cleaned / aligned / normalized /
  filtered before the method sees them.

Cross-domain examples:
- ML: dataset + tokenizer/augmentations.
- Physics: measurement set + filter / detrend / calibrate.
- Chemistry: compound set + purification / preparation.
- Biology: cohort or sequencing reads + alignment / QC.

## 1. Trace the dependencies

```
trace_dependency(component="data")
trace_dependency(component="preprocessing")
```

## 2. Identify the canonical source

Each `data` atom has a `defined_by_paper_id`. That paper is the
canonical source of:

- Splits / batches / cohort sizes.
- Class / label / condition definitions.
- Inclusion / exclusion criteria.
- Preprocessing assumed by the benchmark.

Pull it:

```
paper_text(paper_id="<defining_paper_id>", section_type="experiments")
```

then paragraph-filter to the exact spec.

## 3. Surface preprocessing details

The **target paper's** experiments / methods section is where custom
preprocessing usually lives (not the dataset's defining paper). Search
the corpus:

```
query_chunks(query="<data name> preprocessing normalization filtering",
             limit=8)
```

For each hit the snippet tells you which paper + section. Pull the
chunk full-text only when the snippet looks load-bearing.

## 4. Resolve gaps

```
list_missing_details()
```

Preprocessing is the highest-rate source of missing details in
compiled briefs across every field. For each gap, name an explicit
default in the TODO list.

## 5. Implement

- Mirror the order of operations from the verbatim span exactly.
  Composition order matters in every domain (image augmentations,
  signal-processing chains, sample-prep steps, sequencing pipelines).
- Honor exact numerical constants (mean, std, threshold, cutoff)
  from the defining paper, not approximate values from memory.
- For sequence / molecular / spectral data, exact tokenizer or
  fingerprint encoder matters; cite the chunk.
- If the data isn't accessible in your environment (paywall, license,
  ethics review), stub the loader with a docstring listing the schema
  and a TODO.

## Watch-out list (cross-domain)

ML datasets / preprocessing:
- **Mean / std.** Different per dataset; never assume ImageNet values
  for non-ImageNet data.
- **Crop sizes.** Train and eval often differ.
- **Tokenizer special tokens.** BOS / EOS / pad inclusion changes loss
  computation.
- **Augmentation magnitudes.** RandAug `m=9` and `m=15` are not
  interchangeable.
- **Sampling.** Iterable vs map-style, with or without replacement.

Physics / experimental data:
- **Units and reference frame.** Detector frame vs lab frame; SI vs
  natural units.
- **Calibration constants.** Apply per-run or globally.
- **Background subtraction window.** Affects downstream statistics.

Chemistry data / compound sets:
- **Tautomer / protonation state.** Standardize consistently.
- **Stereochemistry.** Include or strip; it changes the search space.
- **Salt / fragment removal.** Often implicit in the defining paper.

Biology / sequencing / cohort data:
- **Reference genome version.** Changes coordinates downstream.
- **Read-quality filter thresholds.** Affects coverage estimates.
- **Inclusion / exclusion criteria.** Sample size sanity check.

## Verification checklist

- [ ] `atom_uid`s cited for each data + preprocessing step.
- [ ] Tokenizer / encoder / pipeline identified by exact name + version.
- [ ] Splits / cohorts / sample counts match the defining paper.
- [ ] All gaps from `list_missing_details()` resolved with explicit
      defaults.
- [ ] Data stub or real loader produces one valid sample.
