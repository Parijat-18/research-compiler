# implement-baseline — cross-domain watch-outs

## ML / CS baselines
- **Inference resolution.** Baselines often evaluated at their native resolution.
- **Pretrained checkpoints.** Target paper usually used the baseline's released weights — name the checkpoint URL in a TODO.
- **Training budget cap.** "Matched compute" means retrained.

## Physics / simulation baselines
- **Reference simulation parameters.** Time step, ensemble, system size.
- **Force-field version.** Affects every downstream number.

## Chemistry / wet-lab baselines
- **Standard conditions used.** Sometimes "control reaction" means a literature procedure with a specific reference — chase that citation.

## Biology baselines
- **Comparator dataset and version.** Reference panel matters.

## Verification checklist

- [ ] Baseline `atom_uid` + `paper_id` cited.
- [ ] Re-uses the target paper's data + eval pipeline.
- [ ] Variant chosen matches the comparison table / figure in the target paper.
- [ ] Open assumptions in TODO.
