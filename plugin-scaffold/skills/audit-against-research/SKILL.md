---
name: audit-against-research
description: Use this skill when finishing an implementation, reviewing a PR, or when the user asks to verify that code matches the paper. Cross-checks the repository against research/research.md and the paper-compiler MCP graph, flags missing or divergent components, and produces an audit report.
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
---

# Audit implementation against compiled research context

## Trigger

Activate when **any** of the following:

- The user asks to review, audit, or verify the implementation against the paper.
- The user has just finished a major implementation milestone (e.g. "I think I'm done").
- A PR is being prepared from work originating in a paper.

## Procedure

1. **Read `research/research.md`** to load the expected implementation atoms.
2. **List required atoms** via `graph_stats()` and the architecture / loss / dataset / evaluation traces.
3. **For each required atom**, search the repo for evidence of implementation:
   - Use `Grep` / `Glob` to find candidate files.
   - Read the implementing code.
   - Compare against `get_evidence(<atom-id>)`.
4. **Score each atom** as: `IMPLEMENTED`, `PARTIAL`, `MISSING`, `DIVERGENT`.
5. **For each non-IMPLEMENTED atom**, generate a one-line summary of the gap.
6. **Cross-check `list_missing_details()`** — for every open assumption, confirm the code makes a visible choice and that choice is justified.
7. **Produce the audit report** using the template below.

## Audit report template

```
Paper: <title>
Atoms expected: <N>
- Implemented: <count>
- Partial:     <count>
- Missing:     <count>
- Divergent:   <count>

Findings:
- [MISSING]   <atom-name>: <one-line gap>
- [DIVERGENT] <atom-name>: <code says X, brief says Y>
- [PARTIAL]   <atom-name>: <what's there, what's not>

Open assumptions still unflagged in code:
- <missing-detail-id>: <one-liner>

Recommended next steps:
1. ...
```

## Rules

- Only flag DIVERGENT when you have evidence from the MCP graph that contradicts the code. Mere stylistic disagreement is not divergence.
- For ambiguous atoms (e.g. "preprocessing"), require the code to make a single, named, commented choice — not "any of these would work."
- Do not auto-fix divergences. Surface them. The user decides.
- The audit report is the deliverable. Keep it short, structured, and unhedged.
