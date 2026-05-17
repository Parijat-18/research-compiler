---
name: use-research-context
description: Use this skill whenever the user asks to implement, port, reproduce, modify, or extend code from a research paper in a repository that contains a research/ directory with research.md. This skill instructs you to consult the compiled research context before writing implementation code and to query the paper-compiler MCP tools for any specific implementation decision.
allowed-tools:
  - Read
  - mcp__paper-compiler__paper_summary
  - mcp__paper-compiler__trace_dependency
  - mcp__paper-compiler__find_atom
  - mcp__paper-compiler__get_evidence
  - mcp__paper-compiler__list_missing_details
  - mcp__paper-compiler__equation_lookup
  - mcp__paper-compiler__compare_methods
  - mcp__paper-compiler__citation_neighbors
  - mcp__paper-compiler__graph_stats
---

# Use compiled research context for paper implementation

## Trigger

Activate when **both** are true:

1. The user is asking for implementation work that originates from a paper.
2. The current repository contains `research/research.md`.

If only (1) is true and there is no `research/`, tell the user a research context has not been compiled and suggest `/paper-compiler:build-research-context <paper>`.

## Procedure

1. **Read `research/research.md` first.** Always. Before any planning. Before any code.
2. **For each major implementation decision**, query the paper-compiler MCP tools:
   - Architecture component? → `trace_dependency("architecture")`.
   - Loss function? → `trace_dependency("loss")`.
   - Dataset / preprocessing? → `trace_dependency("dataset")` / `trace_dependency("preprocessing")`.
   - Evaluation protocol? → `trace_dependency("evaluation")`.
   - Baseline? → `trace_dependency("baseline")`.
   - Specific question about a component? → `find_atom(<keyword>)` then `get_evidence(<atom-id>)`.
3. **Before adopting any detail not stated in the target paper**, check `list_missing_details()`. If the detail is listed there, the paper + neighborhood do not determine it. Treat it as an explicit assumption and surface the choice.
4. **Cite evidence in code comments** for non-obvious choices, in the form: `# per research/evidence/<atom-id>.md`.

## Rules

- **Do not** rely on model memory for paper-specific implementation details when the brief is available. Prefer the brief and the MCP tools.
- **Do not** rephrase the brief back to the user — it is already in context. Read it, query specifics, then write code.
- If the brief disagrees with the paper PDF as you read it, trust the brief — it is grounded in the citation neighborhood. Surface the disagreement to the user.
- When a detail is genuinely undetermined (listed in `missing-details.md`), make the assumption visible in the code: name it, comment it, and add it to a TODO list at the end of your response.
- Stay concise. The user wants code that matches the paper, not a recap of the paper.
