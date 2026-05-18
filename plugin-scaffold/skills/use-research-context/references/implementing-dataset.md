# Playbook — implementing dataset / preprocessing pipeline

Datasets and preprocessing live in two categories in the atom graph:
`dataset` (which corpus) and `preprocessing` (how it is transformed).

## 1. Trace the dependencies

```
trace_dependency(component="dataset")
trace_dependency(component="preprocessing")
```

## 2. Identify the canonical source

Each dataset atom has a `defined_by_paper_id`. That paper is the canonical
source of:

- Splits (train / val / test sizes).
- Class definitions.
- Preprocessing assumed by the benchmark.

Pull it:

```
paper_text(paper_id="<dataset_paper_id>", section_type="experiments")
```

then paragraph-filter to the exact spec.

## 3. Surface preprocessing details

The target paper's *implementation details* / *experiments* section is where
custom preprocessing lives. Search the corpus:

```
query_chunks(query="<dataset name> preprocessing tokenization augmentation", limit=8)
```

For each hit, the snippet tells you which paper + section. Pull the chunk
full-text only when the snippet looks load-bearing.

## 4. Resolve gaps

```
list_missing_details()
```

Preprocessing is the highest-rate source of missing details in compiled
briefs. For each gap, name an explicit default in the TODO list.

## 5. Implement

- Mirror the order of operations from the verbatim span exactly. Composition
  order matters (e.g. `RandomResizedCrop → Normalize` ≠ `Normalize →
  RandomResizedCrop`).
- Honor mean / std with full precision from the dataset paper, not
  approximate values from memory.
- For sequence datasets, exact tokenizer matters; cite the tokenizer chunk.
- If the dataset isn't downloadable in your environment (login wall, EULA),
  stub the loader with a docstring listing the schema and a TODO.

## Watch-out list

- **Mean / std**. Different per dataset; never assume ImageNet values for
  non-ImageNet data.
- **Crop sizes / aspect ratios**. Train and eval often differ.
- **Tokenizer special tokens**. BOS / EOS / pad inclusion changes loss
  computation.
- **Augmentation magnitudes**. RandAug `m=9` and `m=15` are not interchangeable.
- **Sampling**. Iterable vs map-style, with or without replacement.

## Verification checklist

- [ ] Atom_ids cited for each dataset + preprocessing step.
- [ ] Tokenizer / encoder identified by exact name + version.
- [ ] Splits match the dataset paper's experiment section.
- [ ] All gaps from `list_missing_details()` resolved with explicit defaults.
- [ ] Dataset stub or real loader compiles + produces one valid sample.
