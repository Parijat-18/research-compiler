---
name: resume-session
description: Resume from a prior session. Use when the user says "continue from yesterday", "what was I doing", "pick up where we left off", or returns to a paper repo after time away. Top-level entry point — doesn't assume the user is mid-implementation (use `/paper-compiler:use-research-context continue` for that). Surfaces a one-screen summary of recent sessions and decisions, then dispatches.
disable-model-invocation: true
allowed-tools:
  - Bash
  - mcp__paper-compiler__get_paper_context
  - mcp__paper-compiler__list_sessions
  - mcp__paper-compiler__resume_session
  - mcp__paper-compiler__get_decisions_since
  - mcp__paper-compiler__list_missing_details
---

# resume-session — what was I doing?

Manual-only entry point for re-engagement. The `continue` sub-skill under `use-research-context` does the same for the "I'm mid-implementation" case; this top-level skill is for the broader "I forget what state this repo is in".

## Procedure

1. **Sanity check.** If no `research/` is in scope (the SessionStart hook didn't fire a context block), say so and suggest `/paper-compiler:build-research-context <id>`.

2. **Pull state in three MCP calls** (no file reads):
   ```
   mcp__paper-compiler__get_paper_context()
   mcp__paper-compiler__list_sessions(limit=5)
   mcp__paper-compiler__get_decisions_since(since="<last_session_date - 7 days>")
   ```

3. **Optionally pull the most recent session in full:**
   ```
   mcp__paper-compiler__resume_session(session_id=<most_recent>)
   ```
   Returns: atoms touched, files modified, decisions referenced, next-steps if recorded.

4. **Open missing-details** (what's still un-spec'd):
   ```
   mcp__paper-compiler__list_missing_details()
   ```

5. **Surface a one-screen summary**:

   ```
   📄 Paper: <title>
        <atoms_extracted> atoms across <n_categories> categories
        <papers_in_neighborhood> papers in neighborhood

   🕐 Last session: <date> — <slug>
        Atoms touched: <list>
        Files modified: <list>
        Next steps recorded: <list or "none">

   📝 Recent decisions (since prior session):
        <slug>: <one-line>
        ...

   ❓ Open missing-details: <count>
        (call list_missing_details for detail)

   👉 Suggested next move:
        - If user picks up the previous next-steps  → /paper-compiler:use-research-context continue
        - If user wants to audit current state      → /paper-compiler:audit-against-research
        - If user has a new question on the corpus  → /paper-compiler:wiki-query "<question>"
        - If user wants to add a new related paper  → /paper-compiler:wiki-ingest <id>
   ```

6. **Wait for the user to pick a direction.** Don't auto-dispatch — this is a re-orientation skill, not an action skill.

## Rules

- **No writes.** This is a survey skill; recording new decisions or session notes happens in the dispatched skills.
- **Tight, scannable summary.** The user is re-engaging; minimize the cognitive cost of catching up.
- **Cite session ids and decision slugs** so the user can drill in via `resume_session(session_id=...)` or `get_decisions_since(...)`.
