---
name: wiki-lint
description: Manually invoked. Health-checks the compiled wiki — broken `[[wikilinks]]`, orphan atom pages, atoms whose defining paper is no longer in the DB. Emits `wiki/lint-report.md`. Warn-only in v2 — no auto-fix.
disable-model-invocation: true
context: fork
agent: general-purpose
allowed-tools:
  - Bash
  - Read
  - Write
  - mcp__paper-compiler__schema_doc
  - mcp__paper-compiler__list_missing_details
---

# wiki-lint — health check the wiki + DB

v2.0: the structural sweep is a script (`scripts/lint-wikilinks.sh`). The skill body is a thin wrapper that runs the script, interprets the JSON, and writes a human-readable report. No procedural markdown for Claude to execute step-by-step.

## Procedure

1. **Run the lint script:**
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/scripts/lint-wikilinks.sh research/
   ```
   Output: JSON on stdout, human-readable summary on stderr. Exit codes: 0 clean, 1 issues found, 2 infrastructure failure (no DB / no wiki/).

2. **Parse the JSON** and surface a structured summary. Fields:
   - `broken_wikilinks.{count, items}` — `[[X]]` references that don't resolve to any atom_uid, paper-<safe-id>, community-<N>, or wiki file basename.
   - `orphan_atoms.{count, items}` — atom pages with zero inbound references.
   - `stale_defining.{count, items}` — atoms whose `defined_by_paper_id` no longer exists in the `papers` table.

3. **Cross-check open assumptions.** `mcp__paper-compiler__list_missing_details()`. For each open question, the user can decide whether the corresponding wiki/answers/ file resolves it.

4. **Write `research/wiki/lint-report.md`** with sections:
   ```
   ## Broken wikilinks
   ## Orphan atoms
   ## Stale defining papers
   ## Open missing-details
   ```
   Empty sections become `_clean_`. Cite each finding's atom_uid or paper_id so the user can act.

5. **Append a one-line `lint` entry to `research/wiki/log.md`** with summary counts (the existing `wiki_log.py` writer follows this format).

## Rules

- Warn-only. Never delete or rewrite generated articles.
- The script is the source of truth — don't replicate its checks in the skill body.
- If the script exits 2 (no DB / no wiki/), stop and tell the user to compile first.
