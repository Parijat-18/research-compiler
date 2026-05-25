---
name: continue
description: Resume mid-implementation. Use when the user says "continue", "where were we", "pick up where I left off", "what's next", or returns to a repo with prior `audit-report.md` or `research/sessions/*.md`. Reconstructs progress from session notes + decisions log + missing-details and dispatches to the right next-step sub-skill.
when_to_use: Auto-invoke when prior `research/sessions/*.md` files exist AND the user's prompt indicates continuation (resume, pick up, continue, what's next, where were we).
context: fork
allowed-tools:
  - Bash
  - Read
  - mcp__paper-compiler__get_paper_context
  - mcp__paper-compiler__list_sessions
  - mcp__paper-compiler__resume_session
  - mcp__paper-compiler__get_decisions_since
  - mcp__paper-compiler__list_missing_details
  - mcp__paper-compiler__trace_dependency
---

# continue — resume mid-implementation

The user is picking up work on a paper they previously started. Don't make them re-explain. Reconstruct state from session notes + decisions and propose the next action.

## Procedure

1. **Reconstruct progress** (one script call):
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/scripts/reconstruct-progress.sh
   ```
   Emits JSON: most recent session id + date, atoms touched, files modified, decisions since the prior session, open missing-details count.

2. **Cross-check with MCP** (structured, no file reads):
   ```
   mcp__paper-compiler__list_sessions(limit=3)
   mcp__paper-compiler__resume_session(session_id=<most_recent>)
   mcp__paper-compiler__get_decisions_since(since=<prior_session_end>)
   mcp__paper-compiler__list_missing_details()
   ```

3. **Surface a checkpoint** (concise, one-screen):
   ```
   Last session: <YYYY-MM-DD> — <slug>
   You finished:
     - <atom_uid> <name> (<category>)
     - ...
   Still open:
     - <atom_uid> <name> (<category>) — priority <pri>
     - ...
   Recent decisions (refer to `research/decisions.md`):
     - <slug>: <one-line summary>
   Open assumptions: <count>
   ```

4. **Dispatch.** Suggest the next sub-skill based on the highest-priority open category. Either the user confirms or names a different category, then:
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/scripts/select-playbook.sh "<category>"
   ```
   And invoke the named sub-skill.

## Rules

- **Don't re-implement what's already done.** Use the atoms-touched list to skip completed work.
- **Don't ignore decisions.** A recent `record_decision` may change what should happen next (e.g. "we switched from contrastive to MSE — re-do the audit accordingly").
- **If reconstruction fails** (no prior sessions, empty decisions): tell the user this looks like a fresh start and suggest the parent `use-research-context` router instead.
