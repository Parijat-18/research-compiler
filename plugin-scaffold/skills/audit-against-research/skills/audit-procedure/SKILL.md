---
name: audit-procedure
description: Audit `procedure` and `parameter` atoms (optimizer/integrator/protocol + their parameter values) against the implementation.
when_to_use: Auto-invoked by parent audit skill when `procedure` or `parameter` atoms exist.
context: fork
allowed-tools:
  - Read
  - Grep
  - Glob
  - mcp__paper-compiler__find_atom
  - mcp__paper-compiler__get_evidence
  - mcp__paper-compiler__trace_dependency
---

# audit-procedure

## Recipe

1. `mcp__paper-compiler__trace_dependency(component="procedure")` and `component="parameter"`.

2. For each procedure atom:
   - Grep the procedure name; grep its parameters.
   - Compare with the paper's training-details / methods chunk via `mcp__paper-compiler__get_evidence`.
   - Check common silent divergences:
     - ML: missing `ema_decay`, wrong optimizer eps, wrong gradient clipping value.
     - Physics: missing thermostat coupling, wrong time-step order.
     - Chemistry: missing temperature ramp, wrong order of addition.
     - Biology: missing wash-step count, wrong read-quality filter cutoff.

3. For each parameter atom:
   - Grep the parameter name as a literal or variable.
   - Confirm the value matches the paper.
   - Tolerance: exact match for integer / count values; ±5% for float parameters not otherwise constrained (or the paper's reported precision).

4. **Score** per `audit-method`'s scale.

## Output

Append to `audit-report.md` under `### procedure` and `### parameter`.
