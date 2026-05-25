---
name: implement-objective
description: Implement an `objective` atom — the function being optimized or measured. ML: loss function. Physics: Hamiltonian/action. Chemistry: yield target. Biology: fitness function.
when_to_use: User mentions implementing a loss, objective, regularizer, energy/Hamiltonian, yield target, fitness function, or any scalar function the paper optimizes or evaluates.
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
  - mcp__paper-compiler__equation_lookup
  - mcp__paper-compiler__list_missing_details
  - mcp__paper-compiler__record_decision
---

# implement-objective

The function the paper optimizes or measures. Same MCP flow regardless of domain.

## Procedure

1. **Trace the chain.** `trace_dependency(component="objective")` returns ordered atoms + defining papers. The first atom is usually the one to implement.

2. **Pull verbatim definition.** `get_evidence(atom_id=...)`. If span is too short: `paper_text(paper_id=<defining>, section_type="method")`, narrow to specific paragraphs with `full=True`.

3. **Resolve the math.** `equation_lookup(symbol_or_keyword=...)` to cross-check sign, normalization, indexing convention, expectation scope (per-sample / per-batch / per-ensemble / per-time-step).

4. **Find parameter values.** Numbers (temperature, weight decay, step size, pH) usually live in the **target paper's** experiments section, not the defining paper's. Use `query_chunks(query="<name>", prefer_kind="table")` — the Phase 6 table indexing surfaces ablation tables where these live. For unresolvable values, `list_missing_details()` tells you what's not in the corpus.

5. **Implement.**
   - Match reduction (`mean` vs `sum`; per-sample vs ensemble; per-time-step vs total).
   - Branchless and small — these are the most-audited lines in any field.
   - For asymmetric formulations (contrastive setups, free-energy estimators), implement both directions and verify with a 4-sample (or 4-step) synthetic test.

## Decision capture

When the paper omits a number and you pick a reasonable default, or when the paper's prose is ambiguous and you commit to one reading: `record_decision(category="objective", atom_uid=..., decision=..., why=...)`.

## See also

- `references/watchouts.md` — cross-domain pitfalls (sign, temperature placement, padding/mask exclusion, units, internal standards).
