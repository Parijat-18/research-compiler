---
name: use-research-context
description: Implementation work derived from a compiled paper. Domain-neutral — ML, physics, chemistry, biology, economics, climate, etc. Routes to a category-specific sub-skill (implement-method / implement-objective / implement-data / implement-procedure / implement-evaluation / implement-baseline / debug-divergence) via `scripts/select-playbook.sh`.
when_to_use: Activates when the repo contains `research/research.md` and the user is doing implementation work originating from a paper, regardless of field.
allowed-tools:
  - Bash
  - mcp__paper-compiler__get_paper_context
  - mcp__paper-compiler__list_sessions
  - mcp__paper-compiler__list_missing_details
  - mcp__paper-compiler__route_query_only
---

# use-research-context — router

This is a **dispatcher**, not an implementation skill. Each atom category has its own sub-skill with a tight tool whitelist and a `context: fork` policy island. Pick the right sub-skill and hand off.

## Procedure

1. **Load the structured paper context** via the MCP tool — do **not** Read `research/research.md` directly:
   ```
   mcp__paper-compiler__get_paper_context()
   ```
   Returns paper title + id, atom counts by category, top-priority atoms, top communities, open `missing_details` count, recent session count, recent decisions count. This is the only one-call summary you should need before dispatching.

2. **Check for resumable work.** `mcp__paper-compiler__list_sessions(limit=3)`. If a recent session exists and the user's prompt hints at continuation ("where were we", "continue", "next step"), invoke `/paper-compiler:use-research-context continue` (sub-skill) before doing anything else.

3. **Dispatch by atom category.** Either the user named a category (loss / encoder / dataset / optimizer / evaluation / baseline), or you can infer one from their prompt. Run the dispatcher:
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/scripts/select-playbook.sh "<user phrase>"
   ```
   Output format: `<category> <sub-skill> <slash-command-path>`.

   Then invoke the named sub-skill. Each sub-skill picks up with its own forked context.

4. **Sub-skills available:**
   - `implement-method` — algorithmic/structural unit (ML architecture, physics scheme, chem route, bio protocol)
   - `implement-objective` — loss/Hamiltonian/yield/fitness function
   - `implement-data` — dataset/measurements + preprocessing
   - `implement-procedure` — optimizer/integrator/protocol + parameters
   - `implement-evaluation` — metrics/diagnostics/statistical tests
   - `implement-baseline` — published comparison method
   - `debug-divergence` — when implementation disagrees with paper
   - `continue` — resume mid-implementation (Phase D)
   - `port` — port to a different repo (Phase D)

## Hard rules (enforced by `.claude/settings.json` deny patterns)

- **Do not** `Read` / `Glob` / `Grep` `research/wiki/atoms/`, `research/wiki/papers/`, `research/wiki/communities/`, `research/evidence/`, `research/graph.json`, `research/research.db`. Use the MCP tools — they return structured snippets and are autoApproved.
- `research/research.md` is allowed but unnecessary — `get_paper_context()` gives you the same structured information in less context.
- Cite `atom_uid` (the v1.0 stable id) in code comments, not the sequential `atom_id` (resh­uffles on rebuild).
- Significant choices and gotchas → `record_decision(...)` (requires user approval; lands in `research/decisions.md` and is visible to future sessions).
