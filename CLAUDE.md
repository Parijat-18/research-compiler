# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

`research-compiler` is a Claude Code **plugin** (not a standalone CLI) that compiles a research paper plus its citation neighborhood into a Graph RAG store under `research/`. The plugin source lives entirely in `plugin-scaffold/`; the repo root is a documentation + scaffold container.

`plugin-scaffold/CLAUDE.md` contains workflow conventions that apply **inside a consumer repo that has a `research/` directory** (read brief first, prefer `mcp__paper-compiler__*` over recall, etc.). Those rules are not about *developing this plugin* — they are loaded by the plugin into the user's session. Do not confuse them with build instructions here.

## Three-plane architecture (the load-bearing invariant)

```
CLI (cli/)              →  writes research/   (compile-time only)
research/ artifact      →  on disk, git-friendly, ~26 MB/paper
MCP server (server/)    →  reads research/    (runtime only, read-only)
```

The CLI **never** serves queries. The MCP server **never** writes. Anything that blurs this boundary is a bug. The wiki, DB, and evidence/ are all pure functions of `graph.json` + parsed IR — regenerable from cache without re-acquiring papers.

## Pipeline (9 stages, content-addressed cache at `~/.cache/paper-compiler/`)

`resolve → acquire → parse → expand → classify → atom-extract → score → render → build DB → communities → wiki`

Entry points in `plugin-scaffold/cli/src/paper_compiler_cli/`:
- `cli.py` — argparse dispatch
- `compile.py:build_paper` — the orchestrator; read this to understand the flow
- `resolve.py`, `acquire.py`, `parse/{tex,pdf}.py`, `expand.py`, `classify/{heuristic,llm,edge}.py`, `atoms/{extract,dedup}.py`, `score.py`, `render/*`, `graph_db.py`, `communities.py`
- `ingest.py` — single-paper delta append into an existing `research/`
- `llm.py` — backend selection: `claude_cli` (subscription auth via `claude -p`) > Anthropic SDK > none (heuristic-only)
- `s2_client.py` — Semantic Scholar resolver; `SEMANTIC_SCHOLAR_API_KEY` strongly recommended

Re-runs after parser/classifier fixes are cheap: the cache key is content-addressed, so only the affected stages re-run.

## Common commands

```bash
# Editable install (from repo root)
pip install -e plugin-scaffold/cli[graph,indexes] \
            -e plugin-scaffold/server[vector]
# Optional: PDF parsing (Marker)
pip install -e "plugin-scaffold/cli[pdf]"

# CLI direct invocation (bypasses Claude Code)
plugin-scaffold/cli/bin/paper-compiler resolve <arxiv-id|doi|s2-id|url>
plugin-scaffold/cli/bin/paper-compiler build <paper-id> --out research/
plugin-scaffold/cli/bin/paper-compiler build <paper-id> --no-llm        # heuristic-only smoke test
plugin-scaffold/cli/bin/paper-compiler build <paper-id> --refresh       # invalidate cache for target
plugin-scaffold/cli/bin/paper-compiler ingest <paper-id> --research-dir research/
plugin-scaffold/cli/bin/paper-compiler parse <paper-id> --out /tmp/paper.json   # parse-only debugging

# Load plugin into a fresh consumer session
mkdir -p /tmp/test-impl && cd /tmp/test-impl && git init
claude --plugin-dir /path/to/research-compiler/plugin-scaffold
```

In a Claude Code session with the plugin loaded:
```
/paper-compiler:build-research-context arxiv:<id>     # manual-invoke, runs in forked subagent
/paper-compiler:wiki-ingest <id> | wiki-query <q> | wiki-lint
/paper-compiler:audit-against-research                # auto-invokes when research/ exists
```

No test suite is wired in this repo. Validation today is end-to-end: run a build and check `research/build-manifest.json` for `papers_in_neighborhood ≥ 5`, `coverage_pct ≥ 50`, `atoms_extracted ≥ 8` (the gates `build-research-context` enforces).

## Config & secrets

`paper_compiler_cli/config.py` defines the dataclass-backed schema. Loading order:
1. `.env` and `paper-compiler.env` in cwd (auto-sourced)
2. `--config <path>` → `./paper-compiler.toml` → `~/.config/paper-compiler/config.toml`
3. Env fallbacks: `SEMANTIC_SCHOLAR_API_KEY`, `ANTHROPIC_API_KEY`
4. CLI flag overrides via `apply_overrides()`

Tunables that change pipeline behavior (not just budgets): `compile.expand_top_k`, `compile.atom_paper_count`, `compile.classifier_llm_max_calls`, `compile.atom_llm_max_calls`. The Louvain resolution is hardcoded at 1.4 in `communities.py` and is a known magic number.

## MCP server surface

`plugin-scaffold/server/src/paper_compiler_mcp/`:
- `server.py` — FastMCP app, 15+ tools, lazy graph/DB load on first call
- `db.py` — sqlite + sqlite-vec + FTS5 hybrid retrieval; safe-SQL guard for `graph_sql`
- `graph.py` — networkx wrapper over `graph.json`

Server reads `PAPER_COMPILER_RESEARCH_DIR` (set by `.mcp.json` to `${PWD}/research`). Cold start ~1.5 s for `bge-small` embedding model; cached in module state after.

## Skills

`plugin-scaffold/skills/<name>/SKILL.md` — each has frontmatter (`name`, `description`, `when_to_use`, `disable-model-invocation`, `context`, `allowed-tools`). Heavy task-specific guidance lives in `references/<task>.md` and is **only** loaded when the skill body explicitly points to it. Keep skill bodies ≤ 100–150 lines.

`build-research-context` is the only `context: fork` skill — it runs the compile in a subagent so the main session doesn't see intermediate stage output.

## Known sharp edges (when modifying)

- **Atom ids are sequential and reshuffle on every compile.** Wiki `answers/` files can point at the wrong atom after a rebuild. Stable ids = `(category, canonical_name)` hash; this is a v0.3 blocker.
- **Quality filter drops ~60% of chunks** before FTS5/vec indexing. Tables, captions, references list are excluded. Touching the filter in `graph_db.py` affects recall significantly.
- **Wiki articles regenerate wholesale.** Only `wiki/answers/` survives across rebuilds.
- **`equation_lookup` MCP tool is a stub.** Table is populated; client wiring missing.
- **`paper-compiler cache prune` is a stub.** Cache grows monotonically (50–200 MB/paper).
- **`graph_sql` SELECT/WITH check is prefix-based.** Safe locally; not network-safe.

## External skills available in this session

These are not part of this repo but are loaded into the user's Claude Code and useful when working here.

**graphify** (`/graphify` — `~/.claude/skills/graphify/SKILL.md`)
- "any input (code, docs, papers, images) → knowledge graph → clustered communities → HTML + JSON + audit report"
- Use when the user wants a one-shot graph over arbitrary files outside the paper-compiler pipeline (e.g. graph this codebase, graph the `docs/` folder, query a folder of PDFs). Has its own `query`, `path`, `explain` subcommands and emits to `graphify-out/`.
- Do **not** use as a substitute for `paper-compiler build` — paper-compiler is the right tool for citation-neighborhood compiles with stable atom ids, evidence files, and the MCP query surface.

**claude-mem** (cross-session persistent memory; the `$CMEM` index is loaded at session start)
- `claude-mem:mem-search` — "did we already solve this?", "how did we do X last time?" Search before re-deriving. The session-start banner lists observation IDs (e.g. `2226`, `S479`); fetch with `get_observations([IDs])` via `mcp__plugin_claude-mem_mcp-search__*` tools.
- `claude-mem:smart-explore` — token-efficient tree-sitter AST exploration. Prefer over `Read`/`Grep`/`Glob` when mapping unfamiliar code in the consumer's repo or when scanning this repo's CLI/server packages structurally.
- `claude-mem:make-plan` + `claude-mem:do` — phased plan creation and subagent execution. Use when the user asks for a multi-step implementation; `make-plan` first, then `do` to execute. Don't invoke autonomously — wait for the user to ask.
- `claude-mem:timeline-report` — narrative of the project's full development history from memory. Use only when explicitly requested.

The `$CMEM` index already shows this project has 50+ observations across sessions S470–S483 covering the v0.2 build, JEPA validation, and the v1 docs pass. When the user references prior work ("the wiki rebuild", "the JEPA build", "what we decided about atom ids"), check mem-search before asking them to re-explain.

## Where to look first

- **Pipeline behavior** → `docs/v1_build.md` (1100+ lines, authoritative implementation reference)
- **PRD + the 11-role edge label set** → `docs/01-PRD.md`
- **Architecture rationale** → `docs/04-architecture.md`
- **Evaluation protocol (A/B/C hypothesis)** → `docs/05-evaluation-plan.md`
- **What a verified build looks like** → README "What a compile actually produces" table (JEPA, 2026-05-18)
