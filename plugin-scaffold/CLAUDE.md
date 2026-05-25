# paper-compiler conventions (v2.0)

This plugin compiles a research paper and its citation neighborhood into an implementation-ready memory under `research/`. Works for any scientific or engineering domain — ML, physics, chemistry, biology, economics, climate, etc.

## Hard rules — enforced by PreToolUse hook

The plugin's `PreToolUse` hook (`scripts/enforce-mcp-access.sh`) blocks direct file reads on the Graph RAG store so it is **only** reachable via MCP tools. The following operations are **blocked** (exit code 2):

- `Read` / `Glob` / `Grep` on `research/wiki/atoms/**`, `research/wiki/papers/**`, `research/wiki/communities/**`, `research/evidence/**`
- `Read` / `Grep` on `research/graph.json`, `research/research.db`, `research/embeddings.{npy,json}`

This is intentional: direct file reads bypass the semantic router, community boosts, evidence-provenance trail, and reranker. Use the MCP equivalent for each:

| Bypassed read | MCP alternative |
| --- | --- |
| `Read research/research.md` | `mcp__paper-compiler__get_paper_context()` |
| `Read research/wiki/atoms/<uid>.md` | `mcp__paper-compiler__get_evidence(atom_id=<id or uid>)` |
| `Read research/evidence/<id>.md` | `mcp__paper-compiler__get_evidence` |
| `Read research/wiki/papers/...` | `mcp__paper-compiler__paper_summary` / `paper_text` |
| `Glob research/wiki/atoms/**` | `mcp__paper-compiler__find_atom` / `trace_dependency` |
| Custom SQL on `research.db` | `mcp__paper-compiler__graph_sql` (read-only escape hatch) |

`research/research.md`, `research/decisions.md`, `research/sessions/*.md`, and `research/CLAUDE-PAPER-CONTEXT.md` are **not** denied — they're human-written/edited markdown.

## Session bootstrap

When a session opens in a `research/`-containing repo, the SessionStart hook (`scripts/session-start.sh`) injects a structured context block including the per-paper `CLAUDE-PAPER-CONTEXT.md` fragment. **Don't `Read research/research.md` afterward** — its structured equivalent is already in your context.

If the hook didn't fire (no `research/` reachable from cwd), say so and suggest `/paper-compiler:build-research-context <id>`.

## Skill routing

The plugin ships parent + sub-skill structure. Pick by user intent:

| Intent | Skill |
| --- | --- |
| Compile a fresh paper | `/paper-compiler:build-research-context <id>` |
| Implementation work, any category | `/paper-compiler:use-research-context` (auto-dispatches to `implement-<category>` sub-skill) |
| Resume mid-implementation | `/paper-compiler:use-research-context continue` |
| Port to a different repo | `/paper-compiler:use-research-context port --target <path>` |
| Code disagrees with paper | `/paper-compiler:use-research-context debug-divergence` |
| Audit my reproduction | `/paper-compiler:audit-against-research` |
| Open question on the corpus | `/paper-compiler:wiki-query "<q>"` |
| Add a related paper | `/paper-compiler:wiki-ingest <id>` |
| Compare two compiled papers | `/paper-compiler:compare-corpora <dirA> <dirB>` |
| "What was I doing?" | `/paper-compiler:resume-session` |

The UserPromptSubmit hook (`scripts/detect-intent.sh`) often suggests the right one based on what the user typed. The suggestion is a hint, not a hard route.

## Session-resume rules

When the user signals continuation ("continue", "where were we", "yesterday", "pick up"), pull state with three MCP calls before doing anything else:

```
mcp__paper-compiler__list_sessions(limit=5)
mcp__paper-compiler__resume_session(session_id=<most_recent>)
mcp__paper-compiler__get_decisions_since(since=<prior_session_date>)
```

Surface a one-screen "atoms done / remaining / recent decisions" checkpoint, then dispatch. **Don't re-implement what's already done** — the sessions list tells you.

## Memory hygiene

Two write tools (gated by `ask` in settings):

- **`record_decision(category, decision, why, atom_uid?, source_chunk_id?, source_paper_id?, slug_hint?)`** — append to `research/decisions.md`. Use for:
  - Defaults adopted when the paper is silent on a parameter.
  - Ambiguous prose resolved one way vs another.
  - Approaches tried that didn't work + the resolution.
  - **NOT** for routine implementation work (Claude will record everything otherwise, drowning the log).
- **`append_session_note(note, kind, session_id?)`** — append to a session file under one of 4 sections: `atom_touched`, `file_modified`, `decision_referenced`, `next_step`. The Stop hook calls this automatically at session end — manual calls during a session are for highlighting load-bearing moments.

Memory survives compiles + ingests + ports. The Phase 1 stable `atom_uid` makes cross-session references safe (`atom_id` reshuffles each rebuild; never use it in `decisions.md` or session notes).

## Code citation discipline

In code comments, cite `atom_uid` (16 hex chars), not `atom_id`:

```python
# per atom_uid abc123def4560000 — InfoNCE loss
# per atom_uid 7f9e2c1b0a5d4836 — leapfrog integrator
```

The uid is content-stable (`sha1(category, canonical_name, defining_paper_id)`) so the comment stays correct across rebuilds. `atom_id` is sequential and reshuffles.

## When tempted to web-search or paraphrase

The compiled brief is the system of record. If you're not sure whether the brief covers a detail, call `list_missing_details()` — it tells you what's *not* in the corpus. That's more valuable than a guess. **Never** invent paper-specific details from training data.

If a paper genuinely isn't in the corpus and you need it, `/paper-compiler:wiki-ingest <id>` adds it without losing prior compile state.
