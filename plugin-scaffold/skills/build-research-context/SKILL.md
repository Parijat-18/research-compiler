---
name: build-research-context
description: Use when the user asks to "build research context", "compile this paper", "ingest <paper>", "refresh research/", or hands you a fresh arXiv / DOI / S2 id and wants the full paper-compiler pipeline run. Forks a subagent that runs the CLI compile end-to-end (resolve → acquire → parse → expand → classify → atoms → DB → wiki) and reports real coverage numbers. Manual-only; Claude never auto-invokes this.
when_to_use: User explicitly mentions building, compiling, ingesting, or refreshing research context for a paper.
disable-model-invocation: true
context: fork
agent: general-purpose
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
---

# Build research context for a paper

You are running as a forked subagent. The main Claude Code session will not see your intermediate work — only your final report. Keep the report tight: paths, real numbers from `build-manifest.json`, and any errors.

## Inputs

The user has invoked `/paper-compiler:build-research-context <ID-or-URL> [extra flags]`. The `<ID-or-URL>` is one of:

- An arXiv ID (e.g. `2310.06825`)
- A DOI
- A Semantic Scholar paper ID
- A URL pointing to any of the above
- A local PDF or TeX tarball path

The user may also pass compile flags after the paper id:

- `--max-depth N` (default 2, max 3) — citation depth.
- `--max-papers N` (default 200) — hard cap on neighborhood size.
- `--top-k N` (default 20) — how many depth-1 papers to expand into depth-2.
- `--max-s2-requests N` / `--max-wall-seconds N` — budget caps.
- `--classifier-llm-calls N` / `--atom-llm-calls N` — LLM call caps.
- `--no-llm` — heuristics only, no LLM passes.
- `--refresh` — invalidate cache for the target paper.

Pass them through verbatim to the CLI build command.

## Procedure

1. **Resolve.** Run `${CLAUDE_PLUGIN_ROOT}/cli/bin/paper-compiler resolve <input>` and parse the JSON output. If `candidates` is empty, stop and report.
2. **Confirm with user if ambiguous.** If `confidence < 0.9` or multiple candidates: stop, list them, ask which one. Do not proceed on a guess.
3. **Compile.** Run `${CLAUDE_PLUGIN_ROOT}/cli/bin/paper-compiler build <paper-id> --out research/ [user flags]`. Streamed stderr will show `expand:`, `classify:`, `dedup:`, `embeddings:` progress lines. This is the long step (5–20 min typical).
4. **Read the build manifest.** Open `research/build-manifest.json` — it has real coverage numbers and failure counts.
5. **Sanity-check the result.** A successful compile should have:
   - `papers_in_neighborhood ≥ 5` (a single-paper "neighborhood" is a failed expansion).
   - `coverage.coverage_pct ≥ 50` (otherwise references didn't resolve).
   - `atoms_extracted ≥ 8`.
   If any of these fails, report the failure and the likely cause from the table in the **Failure modes** section below. Do **not** silently report success.
6. **Report back** using the template below.

## Final report template

```
Compiled <paper title> (<paper-id>).

Outputs:
- research/research.md          (~<N> KB human-readable brief)
- research/SCHEMA.md            (Claude-readable DB reference)
- research/research.db          (sqlite + sqlite-vec + FTS5 Graph RAG store)
- research/wiki/                (Obsidian-style cross-linked articles)
- research/missing-details.md   (<K> open questions)
- research/graph.json           (full atom graph, also in DB)
- research/evidence/            (<E> per-atom verbatim spans)

Compile stats:
- Wall time:           <S>s
- References resolved: <X>/<Y>  (<pct>%)
- Neighborhood:        <P> papers (<acquired> with full text)
- Atoms extracted:     <A>
- Edges classified:    <E>
- Communities:         <C>
- LLM backend used:    <claude_cli | anthropic | none>

Next: review research.md, then ask me to implement. The DB at research/research.db
is queryable via `mcp__paper-compiler__query_chunks`, `paper_text`,
`graph_sql`, etc. See research/SCHEMA.md for the full schema.
```

## Failure modes

| Symptom | Likely cause | Fix |
|---|---|---|
| `papers_in_neighborhood == 0` | TeX/PDF parser found no references AND S2 fallback failed | Verify `SEMANTIC_SCHOLAR_API_KEY` is set; try `--refresh` |
| `coverage_pct < 30` | bib entries lack arxiv/DOI; S2 search couldn't disambiguate | Often acceptable for newer preprints — manually inspect `graph.json` |
| `atoms_extracted < 5` | Method section parsed empty | Check parsed IR at `~/.cache/paper-compiler/parsed/<paper-id>.v1.json` |
| `LLM backend used: none` | No `claude` CLI on PATH and no `ANTHROPIC_API_KEY` | Heuristics only; expect lower atom quality. Install Claude Code or set the key |

## Rules

- Never run `build` without first running `resolve` and surfacing the canonical paper.
- Never edit `research/` files yourself. The CLI is the only writer.
- If `build` exits non-zero, do not retry blindly. Read the error, surface it, ask the user.
- Do not summarize the paper's contents in your report. The summary lives in `research.md`. Your job is to confirm the compile produced **real** numbers.

## Setup notes

The CLI at `${CLAUDE_PLUGIN_ROOT}/cli/bin/paper-compiler` is a Python entrypoint. The base install handles TeX papers + heuristic classification + BM25 search. Optional extras:

```bash
pip install -e "${CLAUDE_PLUGIN_ROOT}/cli[pdf]"      # Marker for PDF papers
pip install -e "${CLAUDE_PLUGIN_ROOT}/cli[indexes]"  # SPECTER2 vector search
```

For LLM-based classification + atom extraction, in order of preference:

1. Run inside a Claude Code session → the CLI auto-detects the `claude` CLI on PATH and reuses your subscription auth via `claude -p`. No API key required.
2. Or set `ANTHROPIC_API_KEY` in `.env` (cwd) or shell env → CLI uses the Anthropic SDK directly.
3. Or pass `--no-llm` → heuristics only.

`SEMANTIC_SCHOLAR_API_KEY` is strongly recommended either way (1 RPS dedicated vs. shared anonymous pool). Put it in `.env` so it survives shell restarts.
