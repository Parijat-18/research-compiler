# implement-method — cross-domain watch-outs

## ML methods
- **Pre-norm vs post-norm.** Original Transformer is post-norm; most modern variants are pre-norm. Check the verbatim span, not memory.
- **Dim multipliers.** "Hidden dim 768, MLP ratio 4" means MLP hidden = 3072. Verify with `equation_lookup`.
- **Positional encoding.** Sinusoidal vs learned vs rotary vs none.
- **Attention masking.** Causal vs bidirectional vs prefix-LM.
- **Initialization scheme.** Cite the chunk.

## Physics / simulation methods
- **Integrator order.** RK2 vs RK4 vs symplectic; energy conservation sensitive to choice.
- **Boundary conditions.** Periodic vs reflecting vs absorbing.
- **Stencil.** Centered vs upwind; affects stability.
- **Units.** Reduced (LJ / natural) vs SI; conversion factors matter.

## Chemistry / wet-lab methods
- **Stoichiometry and order of addition.** Both matter — flag if missing.
- **Solvent / catalyst / temperature.** Often in a parameter atom; cross-reference.
- **Workup and purification.** Frequently in supplementary; query a broader chunk set.

## Biology / sequencing protocols
- **Library prep kit and adapter.** Affects downstream alignment.
- **Read length and pairing.** Affects coverage math.
- **Reference genome version.** Often stated once and assumed.

## Verification checklist (any domain)

- [ ] `atom_uid` cited in code.
- [ ] Implemented against the *defining* paper, not the target's paraphrase.
- [ ] Equations match `equation_lookup` output.
- [ ] Output shapes / quantities pass a dry-run on the expected input.
- [ ] Open assumptions added to TODO list at end of response.
