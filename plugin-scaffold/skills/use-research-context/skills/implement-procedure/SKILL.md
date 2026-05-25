---
name: implement-procedure
description: Implement a `procedure` or `parameter` atom — how the method is RUN. ML: optimizer/scheduler/training loop. Physics: integrator/thermostat/sampling. Chemistry: reaction conditions. Biology: experimental procedure.
when_to_use: User mentions implementing the training loop, optimizer, scheduler, integrator, sampler, reaction conditions, experimental protocol, or setting parameter values.
context: fork
allowed-tools:
  - Read
  - Glob
  - Edit
  - Write
  - mcp__paper-compiler__get_paper_context
  - mcp__paper-compiler__find_atom
  - mcp__paper-compiler__get_evidence
  - mcp__paper-compiler__trace_dependency
  - mcp__paper-compiler__paper_text
  - mcp__paper-compiler__query_chunks
  - mcp__paper-compiler__list_missing_details
  - mcp__paper-compiler__record_decision
---

# implement-procedure

The "how-it-runs" layer. Was conflated with `objective` in v0.2; v1.0 split them. Cross-domain examples:

| Domain | Procedure |
| --- | --- |
| ML | Optimizer + scheduler + training loop |
| Physics | Integrator + thermostat + sampling scheme |
| Chemistry | Reaction conditions + workup + purification |
| Biology | Experimental protocol + readout sequence |

## Procedure

1. **Trace.** `trace_dependency(component="procedure")` for run-time steps. `trace_dependency(component="parameter")` for the values they take.

2. **Pull verbatim.** `get_evidence(atom_id=...)` then `paper_text(paper_id=<defining>, section_type="method")` for surrounding context.

3. **Find values.** Parameters typically live in tables. Use `query_chunks(query="<parameter name>", prefer_kind="table")` — Phase 6 indexes tables as their own `chunk_kind`, so values surface here that prose retrieval would miss.

4. **Resolve missing.** `list_missing_details()` lists what the paper doesn't state. For each, pick a reasonable default + comment + `record_decision(category="parameter", ...)`.

5. **Implement.**
   - Order of operations is load-bearing in every domain (training step order, reaction order of addition, sampling sequence).
   - Match the paper's reduction conventions.
   - For ensemble / replicate runs, mirror the paper's sample size and seeding strategy.

## See also

- `references/watchouts.md` — cross-domain pitfalls (ML EMA / optimizer eps, physics time-step order, chem stoichiometry order, bio reagent timing).
