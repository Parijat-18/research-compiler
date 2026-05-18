# Playbook — implementing evaluation protocol / metric

## 1. Pull eval atoms

```
trace_dependency(component="evaluation")
```

Each atom names a metric or benchmark. The `defined_by_paper_id` is the
canonical metric source.

## 2. Pin metric definitions

Different papers define "accuracy" / "F1" / "BLEU" differently (top-1 vs
top-5, macro vs micro, smoothed vs not). Get the verbatim:

```
get_evidence(atom_id="atom-NNN")
paper_text(paper_id="<defining_paper_id>", section_type="experiments")
```

For non-trivial metrics, also pull the math:

```
equation_lookup(symbol_or_keyword="<metric symbol>")
```

## 3. Identify protocol nuances

These almost never live in the metric atom — they're in the *evaluation
protocol* section:

- Test split definition. Often `val` ≠ `test` and the paper means one.
- Resolution / crop applied at eval.
- Number of inference passes (multi-crop, sliding window, beam size).
- Statistical significance procedure (paired t-test, bootstrap CI).

Search:

```
query_chunks(query="<metric name> evaluation protocol split inference", limit=8)
```

## 4. Cross-paper baselines

If the user is comparing against published numbers, those numbers come from
the cited baseline papers, not the target. Walk:

```
citation_neighbors(paper_id="<target>", role="evaluation_protocol_dependency")
```

Each neighbor's paper_text tells you what scoring conditions produced their
published number.

## 5. Implement

- Reuse a known library (`torchmetrics`, `evaluate`) when the metric is
  standard. Cite the chunk where the paper names the metric.
- Run on one sample and one mini-batch before scaling. Pad / mask correctness
  is the most common eval bug.
- Print metric definition once at startup so logs are self-documenting.

## Watch-out list

- **Top-1 vs top-5 accuracy**. The paper specifies; check.
- **BLEU smoothing**. SacreBLEU defaults are not the original BLEU defaults.
- **F1 averaging**. macro / micro / weighted are different numbers.
- **Eval batch shuffling**. Should be off; usually default-on in custom code.
- **Float dtype at eval**. Some papers report fp32-eval-of-bf16-model; mixing
  changes the third decimal.

## Verification checklist

- [ ] Atom_id cited for each metric.
- [ ] Definition matches verbatim chunk.
- [ ] Eval split is the one named in the experiments section.
- [ ] One reference comparison value reproduces within tolerance.
- [ ] Statistical test (if mentioned in the paper) implemented.
