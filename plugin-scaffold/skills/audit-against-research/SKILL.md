---
name: audit-against-research
description: Cross-check the repo against the compiled paper-compiler context. Domain-neutral — works on ML reproductions, physics simulations, chemistry pipelines, biology protocols. Dispatches per-category audit sub-skills (audit-method / audit-objective / audit-data / audit-procedure / audit-evaluation / audit-baseline / audit-theory). Warn-only — never auto-fixes.
when_to_use: Activates when research/ exists and the user is reviewing, finishing, or PR-prepping paper-derived code, regardless of field.
allowed-tools:
  - Bash
  - Read
  - Write
  - mcp__paper-compiler__get_paper_context
  - mcp__paper-compiler__graph_stats
  - mcp__paper-compiler__trace_dependency
  - mcp__paper-compiler__list_missing_details
---

# audit-against-research — router

Cross-check the repo against the compiled context. Each atom category has its own audit sub-skill with a tight tool whitelist. Per-atom verdicts: `IMPLEMENTED` / `PARTIAL` / `MISSING` / `DIVERGENT`.

## Procedure

1. **Load structured context** via MCP — do **not** Read `research/research.md` directly:
   ```
   mcp__paper-compiler__get_paper_context()
   mcp__paper-compiler__graph_stats()
   ```

2. **Enumerate required atoms.** For each category present (skip categories the paper doesn't use — a pure theory paper has no `procedure` atoms):
   - `mcp__paper-compiler__trace_dependency(component=<category>)` returns the ranked atoms.
   - Cap at top 25 by `priority`.

3. **Run the per-category audit sub-skill** for each category present:
   - `audit-method` — algorithmic/structural unit
   - `audit-objective` — loss / Hamiltonian / yield / fitness
   - `audit-data` — datasets + preprocessing
   - `audit-procedure` — training loop / integrator / experimental procedure + parameters
   - `audit-evaluation` — metrics & statistical tests
   - `audit-baseline` — published comparisons
   - `audit-theory` — theorems / assumptions / principles

4. **Cross-check open assumptions.** `mcp__paper-compiler__list_missing_details()`. Every open assumption must show as a visible choice in the code — comment, named config value, or TODO.

5. **Write `audit-report.md`** at the repo root using the template at `references/audit-report-template.md`.

## Rules

- Flag `DIVERGENT` only with evidence — cite `atom_uid` (stable across rebuilds) + `chunk_id` + `paper_id`. Stylistic disagreement is not divergence.
- Do not auto-fix. The user decides.
- Keep the report short — the user reads it next session.
