# Playbook — implementing a `baseline` atom

A baseline is a published method / system / procedure the target paper
compares against. Use this playbook when the user says "add baseline
X" or "implement the comparison method". Works in any domain — ML
baselines, physics reference simulations, chemistry control reactions,
biology comparator protocols.

## 1. Pull baseline edges

```
citation_neighbors(paper_id="<target_paper_id>", role="baseline_dependency")
```

Returns each baseline as `paper_id + best_confidence + section_type +
context_excerpt`. The excerpt tells you which results table or figure
cited it.

## 2. Pick the minimum spec to reproduce

Don't reimplement the baseline whole. The target paper used it under
specific conditions (one dataset / one run length / one budget). Pull
only what matches:

```
paper_summary(paper_id="<baseline_paper_id>")
paper_text(paper_id="<baseline_paper_id>", section_type="method")
```

If the baseline paper was acquired and parsed, its method section is
in the DB. If not, you'll only have abstract + metadata — flag this in
the TODO and fall back to a single-call query for the protocol:

```
query_chunks(query="<baseline name> setup parameters", limit=6)
```

## 3. Check for official code / artifacts

```
find_atom(query="<baseline name> implementation reference")
```

The atom for the baseline often points to a defining paper that names
an official repo, simulation engine, or measurement instrument. If the
user has those locally, prefer them over re-deriving from the PDF.

## 4. Implement

- Aim for **drop-in API parity** with the target paper's main method —
  same data loader, same evaluation loop, only the method class
  differs.
- If the baseline has multiple variants (small / base / large; v1 / v2
  parameters), implement only the variant the target paper compared
  against. Cite the chunk.
- Reuse existing data and evaluation code from the target
  implementation.

## Watch-out list (cross-domain)

ML / CS baselines:
- **Inference resolution.** Baselines often evaluated at their native
  resolution, not the target's.
- **Pretrained checkpoints.** Target paper usually used the baseline's
  released weights — name the checkpoint URL in a TODO.
- **Training budget cap.** "Matched compute" means retrained.

Physics / simulation baselines:
- **Reference simulation parameters.** Time step, ensemble, system size.
- **Force-field version.** Affects every downstream number.

Chemistry / wet-lab baselines:
- **Standard conditions used.** Sometimes "control reaction" means a
  literature procedure with a specific reference — chase that citation.

Biology baselines:
- **Comparator dataset and version.** Reference panel matters.

## Verification checklist

- [ ] Baseline `atom_uid` + `paper_id` cited.
- [ ] Re-uses the target paper's data + eval pipeline.
- [ ] Variant chosen matches the comparison table / figure in the
      target paper.
- [ ] Open assumptions in TODO.
