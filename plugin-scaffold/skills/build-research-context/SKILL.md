---
name: build-research-context
description: Use when the user asks to "build research context", "compile this paper", "ingest <paper>", "refresh research/", or hands you a fresh arXiv / DOI / S2 id / open-access URL and wants the full paper-compiler pipeline run. Works for any scientific or engineering domain — ML, physics, chemistry, biology, economics, climate, etc.; categories and roles are domain-neutral. Starts the CLI compile as a background process with real-time log monitoring so the user can track progress. Manual-only; Claude never auto-invokes this.
when_to_use: User explicitly mentions building, compiling, ingesting, or refreshing research context for a paper, regardless of field.
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Monitor
  - mcp__paper-compiler__bind_research_dir
  - mcp__paper-compiler__get_paper_context
---

# Build research context for a paper

## Inputs

The user has invoked `/paper-compiler:build-research-context <ID-or-URL> [extra flags]`. The `<ID-or-URL>` is one of:

- An arXiv ID (e.g. `2310.06825`)
- A DOI
- A Semantic Scholar paper ID
- A URL pointing to any of the above
- A local PDF or TeX tarball path

Optional compile flags:

- `--max-depth N` (default 2, max 3) — citation depth.
- `--max-papers N` (default 200) — hard cap on neighborhood size.
- `--top-k N` (default 20) — how many depth-1 papers to expand into depth-2.
- `--max-s2-requests N` / `--max-wall-seconds N` — budget caps.
- `--classifier-llm-calls N` / `--atom-llm-calls N` — LLM call caps.
- `--no-llm` — heuristics only, no LLM passes.
- `--refresh` — invalidate cache for the target paper.

Pass them through verbatim to the CLI build command.

## Procedure

### Step 1 — Resolve

```bash
${CLAUDE_PLUGIN_ROOT}/cli/bin/paper-compiler resolve <input>
```

Parse the JSON output. If `candidates` is empty, stop and report.

### Step 2 — Confirm if ambiguous

If `confidence < 0.9` or multiple candidates: stop, list them, ask which one. Do not proceed on a guess.

### Step 3 — Start build in background

```bash
PAPER_ID=<canonical paper id from resolve>
BUILD_LOG="/tmp/paper-compiler-${PAPER_ID}.log"
RESEARCH_DIR="${CLAUDE_PROJECT_DIR}/research"

mkdir -p "${RESEARCH_DIR}"

${CLAUDE_PLUGIN_ROOT}/cli/bin/paper-compiler build "${PAPER_ID}" \
  --out "${RESEARCH_DIR}" [user flags] \
  > "${BUILD_LOG}" 2>&1
```

Run the above Bash command with `run_in_background: true`.

Tell the user: "Build started for **<title>** (`<paper-id>`). Monitoring `${BUILD_LOG}`."

### Step 4 — Monitor progress

Use the Monitor tool on `"${BUILD_LOG}"` to stream progress as lines appear. Report key markers to the user:

| Log line prefix | Meaning |
|---|---|
| `expand:` | Citation neighborhood expansion |
| `classify:` | Edge classification pass |
| `dedup:` | Atom deduplication |
| `embeddings:` | Vector index build |
| `[build]` or `Done` | Build complete |
| any `ERROR` or `Traceback` | Build failed — surface immediately |

Continue monitoring until the background bash notification fires (build process exits). Then proceed to Step 5.

### Step 5 — Activate MCP tools

Call `mcp__paper-compiler__bind_research_dir` with `research_dir="${RESEARCH_DIR}"`.

This tells the running MCP server to reload from the freshly written `research/`. After this call, all 26 MCP tools (query_chunks, find_atom, get_evidence, graph_sql, etc.) are live against the new research.

If the call returns an error, note it in the report but continue — the user can restart the MCP server manually.

### Step 6 — Validate

Run the validator script:

```bash
${CLAUDE_PLUGIN_ROOT}/scripts/validate-build-manifest.sh "${RESEARCH_DIR}"
```

Exit codes: 0 = all pass; 1 = soft warnings (coverage low / atoms low / single-source); 2 = hard fail (manifest missing / evidence provenance regressed / expansion failed). The script prints PASS/SOFT/HARD per invariant on stderr and a JSON summary on stdout.

Read `${RESEARCH_DIR}/build-manifest.json` for real coverage numbers.

Acceptance invariants (v2.0):
- `papers_in_neighborhood ≥ 5` (HARD)
- `coverage_pct ≥ 70`
- `atoms_extracted ≥ 30`
- `evidence_provenance.resolved_pct == 100.0` (HARD)
- `papers_by_source` has ≥ 2 distinct sources
- papers-with-atoms / papers-acquired ≥ 0.6

If any hard-fails, report the failure and the likely cause from the **Failure modes** table. Do not silently report success.

### Step 7 — Report

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
- Sources used:        <e.g. arxiv_tex: 80, openalex_pdf: 50, unavailable: 96>
- Atoms extracted:     <A>
- Evidence provenance: <E>/<T> (<pct>%)   ← must be 100%
- Edges classified:    <E>  (contradicts: <K>)
- Communities:         <C>
- Wiki answers re-indexed: <W>
- LLM backend used:    <claude_cli | anthropic | none>

MCP status: bind_research_dir called — all 26 MCP tools now queryable.
Next: /paper-compiler:wiki-query "<question>" or /paper-compiler:use-research-context to start implementing.
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
- Always use `${CLAUDE_PROJECT_DIR}/research` as the absolute output path — never `research/` (relative).
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
