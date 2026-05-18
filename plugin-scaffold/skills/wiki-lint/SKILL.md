---
name: wiki-lint
description: Manually invoked. Health-checks the compiled wiki — finds orphan articles (no inbound wikilinks), broken `[[wikilinks]]`, atoms whose defining paper is no longer in the DB, stale `answers/<slug>.md` files whose cited chunks have changed ids, and `missing-details.md` items already resolved by newer pages. Emits `wiki/lint-report.md`. Warn-only in v1 — no auto-fix.
disable-model-invocation: true
context: fork
agent: general-purpose
allowed-tools:
  - Bash
  - Read
  - Write
  - Glob
  - Grep
  - mcp__paper-compiler__graph_sql
  - mcp__paper-compiler__schema_doc
---

# wiki-lint — health check the wiki + DB

## Procedure

1. **Inventory.**
   - `Glob("research/wiki/**/*.md")` → list every article.
   - Build the set of valid ids: `<atom-NNN>` (from `atoms/`), `paper-<safe>`
     (from `papers/`), `community-<n>` (from `communities/`).
2. **Broken wikilinks.** For each article, grep `[[`-references; flag any
   that don't resolve to a known id. Output `wiki/lint-report.md` with one
   bullet per broken link (article → broken id).
3. **Orphans.** Any `atoms/<atom-id>.md` with zero inbound `[[atom-id]]`
   references across the wiki — likely a dead atom. Flag.
4. **Stale defining papers.** `graph_sql("SELECT a.atom_id, a.defined_by_paper_id FROM atoms a LEFT JOIN papers p ON p.paper_id = a.defined_by_paper_id WHERE p.paper_id IS NULL")` — flag.
5. **Resolved missing-details.** Read `research/missing-details.md`; for each
   open question, grep `wiki/answers/` for the question keywords. Flag any
   answer that appears to resolve a still-open question.
6. **Log size.** If `wiki/log.md` is over 500 lines, suggest archiving older
   quarters to `wiki/log-archive-YYYY-QN.md`. Don't move them yourself.
7. **Write** `research/wiki/lint-report.md` with section headers:
   `## Broken wikilinks`, `## Orphan atoms`, `## Stale defining papers`,
   `## Resolved missing-details`, `## Log housekeeping`. Empty sections become
   `_clean_.`.
8. **Append a `lint` entry to `wiki/log.md`** with summary counts.

## Rules

- Warn-only. Never delete or rewrite generated articles. Auto-fix is v2.
- Don't run the LLM. Lint is a structural sweep, not analysis.
- If `research.db` is missing, stop and tell the user to compile first.
