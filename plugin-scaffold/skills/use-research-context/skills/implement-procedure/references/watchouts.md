# implement-procedure — cross-domain watch-outs

## ML optimizers + schedules
- **Optimizer epsilon.** AdamW eps=1e-8 vs 1e-6 changes mixed-precision stability.
- **EMA decay.** Missing `ema_decay` is a common silent divergence.
- **Gradient clipping.** Cited as "clipping" without value; default of 1.0 vs the paper's may differ.
- **Warmup vs cosine vs constant.** Cited together but compose differently.

## Physics simulation procedures
- **Time-step order.** Symplectic vs RK; affects energy conservation.
- **Equilibration cutoff.** Discard first N steps; cite the chunk.
- **Thermostat coupling time.** Affects ensemble equilibration.
- **Replica count + RNG seed.** Reproducibility hinges on both.

## Chemistry procedures
- **Order of addition.** Stoichiometry + order both matter.
- **Reaction time / temperature ramp.** Both in `parameter` atoms; verify per chunk.
- **Workup steps.** Often in supplementary; broader chunk query.

## Biology experimental procedures
- **Sample size / replicates.** Cross-check the evaluation playbook.
- **Statistical test.** A procedure atom; verify the test is appropriate.

## Verification checklist

- [ ] `atom_uid` cited for the procedure and each parameter.
- [ ] Step sequence matches verbatim span.
- [ ] Parameter values from a single named chunk; chunk_id in comment.
- [ ] Synthetic dry-run on 4 steps returns a sensible result.
- [ ] Missing-detail TODO list at end of response.
