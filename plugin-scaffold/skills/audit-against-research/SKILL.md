---
name: audit-against-research
description: Cross-check the repo against the compiled paper-compiler context and flag missing / divergent / partial implementations. Use when finishing a paper implementation, reviewing a PR derived from a paper, or when the user explicitly asks "audit my code against the paper", "is this faithful to <paper>?", "check my reproduction". Produces `audit-report.md` with per-atom verdicts. Warn-only — never auto-fixes.
when_to_use: Activates when research/ exists and the user is reviewing, finishing, or PR-prepping paper-derived code.
paths:
  - research/research.md
  - src/**/*.py
  - "**/*.py"
  - "**/*.ipynb"
allowed-tools:
  - Read
  - Grep
  - Glob
  - mcp__paper-compiler__paper_summary
  - mcp__paper-compiler__trace_dependency
  - mcp__paper-compiler__find_atom
  - mcp__paper-compiler__get_evidence
  - mcp__paper-compiler__list_missing_details
  - mcp__paper-compiler__graph_stats
  - mcp__paper-compiler__neighborhood_subgraph
  - mcp__paper-compiler__graph_sql
---

# audit-against-research

Verdict per atom. Short, structured, unhedged. See
`references/audit-checklist.md` for the per-category audit recipes.

## Procedure

1. Read `research/research.md`.
2. List required atoms via `graph_stats()` + the four traces (architecture,
   loss, dataset, evaluation). Cap at top 25 by `priority`.
3. For each atom, run the category-specific audit from
   `references/audit-checklist.md` and score: `IMPLEMENTED` / `PARTIAL` /
   `MISSING` / `DIVERGENT`.
4. Cross-check `list_missing_details()`: every open assumption must show as a
   visible choice in the code (comment, config value, named variable).
5. Write `audit-report.md` using the template below.

## Audit report template

```
Paper: <title>  (<atom_count> required atoms)

| Status      | Count |
| :---------- | ----: |
| Implemented |   ... |
| Partial     |   ... |
| Missing     |   ... |
| Divergent   |   ... |

## Findings
- [MISSING]   atom-NNN <name>: <one-line gap, file ref if relevant>
- [DIVERGENT] atom-NNN <name>: code says <X>, brief says <Y> (chunk_id=N)
- [PARTIAL]   atom-NNN <name>: <what's there, what's not>

## Unflagged assumptions
- md-NNN: <one-liner>

## Recommended next steps
1. ...
```

## Rules

- Only flag DIVERGENT with evidence (cite chunk_id or atom_id). Stylistic
  disagreement is not divergence.
- Do not auto-fix. The user decides.
- Keep the report short — Claude reads it next session.
