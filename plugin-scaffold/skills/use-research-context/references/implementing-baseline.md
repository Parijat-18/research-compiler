# Playbook — implementing a baseline

A baseline is a published model the target paper compares against. Use this
playbook when the user says "add baseline X" or "implement the comparison
method".

## 1. Pull baseline edges

```
citation_neighbors(paper_id="<target_paper_id>", role="baseline_dependency")
```

Returns each baseline as `paper_id + best_confidence + section_type +
context_excerpt`. The excerpt tells you which results table cited it.

## 2. Pick the minimum spec to reproduce

Don't reimplement the baseline whole. The target paper used it under
specific conditions (one dataset, one resolution, one budget). Pull only what
matches:

```
paper_summary(paper_id="<baseline_paper_id>")
paper_text(paper_id="<baseline_paper_id>", section_type="method")
```

If the baseline paper itself was acquired and parsed, its method section is
in the DB. If not, you'll only have abstract + metadata — flag this in the
TODO and fall back to a single-call query for the protocol:

```
query_chunks(query="<baseline name> training details hyperparameters", limit=6)
```

## 3. Check for official code

```
find_atom(query="<baseline name> implementation reference")
```

The atom for the baseline often points to a defining paper that names an
official repo. If the user has it locally, prefer their code over re-deriving
from the PDF.

## 4. Implement

- Aim for **drop-in API parity** with the target paper's main method — same
  data loader, same eval loop, only the model class differs.
- If the baseline has multiple variants (small / base / large), implement
  only the variant the target paper compared against. Cite the chunk.
- Re-use existing dataset and metric code from the target implementation.

## Watch-out list

- **Inference resolution.** Baselines are often evaluated at the baseline's
  native resolution, not the target's. The numbers depend on it.
- **Pretrained checkpoints.** The target paper usually used the baseline's
  released weights — name the checkpoint URL in a TODO.
- **Training budget cap.** When the comparison is "matched compute", the
  baseline was retrained for that budget; you need to do the same.
- **Pre / post-processing.** Baselines may include their own pre/post stages
  (token filtering, label smoothing) that the target paper inherited.

## Verification checklist

- [ ] Baseline atom_id + paper_id cited.
- [ ] Re-uses the target paper's data + eval pipeline.
- [ ] Variant chosen matches the comparison table in the target paper.
- [ ] Open assumptions in TODO.
