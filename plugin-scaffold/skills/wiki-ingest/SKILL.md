---
name: wiki-ingest
description: Manually invoked. Adds one more paper to the existing compiled research context — fetches it, parses it, runs atom extraction on it, re-clusters communities, and refreshes the wiki articles + index + log. Use when the user says "ingest <paper>", "add this paper to the corpus", or shares a new arxiv/DOI link they want incorporated into the wiki.
disable-model-invocation: true
context: fork
agent: general-purpose
allowed-tools:
  - Bash
  - Read
  - Write
---

# wiki-ingest — add one paper to the compiled corpus

You are running as a forked subagent. Your job is **acquisition + incremental
indexing**, not analysis. Keep the final report tight: counts and a one-line
summary.

## Inputs

`$ARGUMENTS` is a single paper identifier:

- arXiv id (e.g. `2310.06825`)
- DOI
- Semantic Scholar paper id (`s2:<hex>`)
- URL to any of the above
- Local PDF or TeX tarball path

## Procedure

1. **Verify `research/research.db` exists.** If not, stop — point the user at
   `/paper-compiler:build-research-context` first.
2. **Run** `${CLAUDE_PLUGIN_ROOT}/cli/bin/paper-compiler ingest $ARGUMENTS --research-dir research/`. This is the heavy step (1–5 min). It does, in order:
   - Resolve to a canonical paper_id via Semantic Scholar.
   - Refuse if the paper is already in the DB (unless `--force`).
   - Acquire arXiv source / openAccessPdf / local file.
   - Parse to IR using the same parsers as `build`.
   - Run atom extraction (~10 LLM calls).
   - Insert papers/sections/chunks/atoms/edges into `research.db`.
   - Recompute communities + refresh the 10 most-affected wiki articles.
   - Append a `## … — ingest` entry to `wiki/log.md`.
3. **Read** `research/wiki/log.md` and report the new entry verbatim back to the user.

## Rules

- Never bypass the CLI. The wiki articles + DB are kept in sync by the CLI,
  not by hand-edits.
- If the CLI exits non-zero, surface the stderr tail and stop. Do not retry
  blindly — often the paper is unacquirable (closed-access) and the right
  thing is to tell the user.
- Don't summarize the paper's contents in your report. The summary lands in
  the wiki article; your job is to confirm the ingest worked.
