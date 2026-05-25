# Playbook — implementing an `objective` or `procedure` atom

This playbook covers the **function being optimized or measured**
(`objective`) and the **procedure that runs the method**
(`procedure` / training loop / integrator / experimental protocol).
The two atom categories share a flow because the MCP query pattern is
identical — only the recovered text differs.

Cross-domain examples:
- ML: loss function + optimizer + LR schedule.
- Physics: action / Hamiltonian + numerical integrator + time step.
- Chemistry: yield target + reaction conditions + workup.
- Biology: fitness function + experimental procedure + readout protocol.

## 1. Trace the dependency

```
trace_dependency(component="objective")   # or "procedure"
```

Returns the ordered chain of atoms + their defining papers. The first
atom is usually the one to implement.

## 2. Pull verbatim definition

```
get_evidence(atom_id="atom-NNN")
```

If the verbatim span is short, also pull the surrounding paragraph:

```
paper_text(paper_id="<defining_paper_id>", section_type="method")
```

then `paper_text(..., paragraph_ids=[<the right one>], full=True)`.

## 3. Resolve the math / steps

```
equation_lookup(symbol_or_keyword="<lhs symbol or quantity name>")
```

Cross-check sign, normalization, units, and whether expectations are
over batches / time / ensembles. For procedures without equations
(experimental protocols), use:

```
query_chunks(query="<procedure name> step order", prefer_kind="prose")
```

## 4. Parameter values

The numbers (temperature, weight decay, step size, pH, learning rate,
catalyst concentration) usually live in *training/run/experimental*
details in the **target paper**, not the defining paper. Walk:

```
trace_dependency(component="parameter")
find_atom(query="<parameter name>", limit=5)
```

Or, more direct:

```
query_chunks(query="<parameter name>", prefer_kind="table")
```

— the `prefer_kind="table"` boost (Phase 6) surfaces ablation tables
where these values live.

If `list_missing_details()` includes "temperature schedule for X" or
similar, that's the paper *not* specifying. Choose a reasonable default,
comment it, and add it to the TODO list.

## 5. Implement

- Keep objective code branchless and small — these are the most-audited
  lines in any field.
- Match reduction (`mean` vs `sum` for ML; per-particle vs total for
  physics; per-sample vs ensemble for biology).
- For asymmetric formulations (some contrastive setups, some
  free-energy estimators), implement both directions and verify with a
  synthetic 4-sample (or 4-step) test that gives a known answer.

## Watch-out list (cross-domain)

ML objectives + optimizers:
- **Temperature placement.** `softmax(sim / τ)` not `softmax(sim) / τ`.
- **Negative sign.** Many papers write the loss with a leading minus
  that matters only if you re-derive from log-likelihood — copy from
  the verbatim span verbatim.
- **Padding / mask exclusion.** Sequence losses must exclude padded
  tokens. Almost never spelled out.
- **Stop-gradient on EMA target.** Load-bearing when present.
- **Optimizer epsilon.** AdamW eps=1e-8 vs 1e-6 changes mixed-precision
  stability.

Physics / simulation procedures:
- **Time-step order.** Symplectic vs RK; affects energy conservation.
- **Units / nondim factors.** Reduced (LJ) vs SI conversions.
- **Initial / boundary conditions.** Often specified once, far from the
  equation.
- **Convergence criterion.** Wall-time vs error tolerance vs fixed
  iteration count.

Chemistry / wet-lab procedures:
- **Order of addition.** Stoichiometry + order both matter.
- **Reaction time / temperature.** Both in `parameter` atoms; verify
  values per chunk.
- **Workup steps.** Often in supplementary; query a broader chunk set.

Biology / experimental procedures:
- **Sample size / replicates.** A `parameter` atom; cross-check the
  evaluation playbook.
- **Statistical test.** A `procedure` atom; verify the test is
  appropriate.

## Verification checklist

- [ ] `atom_uid` cited in code (preferred over `atom_id`).
- [ ] Equation / step sequence matches verbatim span.
- [ ] Parameter values from a single named chunk; chunk_id in comment.
- [ ] Synthetic dry-run on 4 hand-built samples / steps returns a
      sensible result (positive loss, conserved energy, expected yield,
      etc.).
- [ ] Missing-detail TODO list at end of response.
