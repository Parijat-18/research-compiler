# research-compiler

> A research paper is a compressed implementation artifact. The detail a coding agent needs to actually reproduce it lives *across the citation neighborhood* — in the cited methods, datasets, baselines, prior architectures, evaluation protocols. **research-compiler** is a Claude Code plugin that compiles that neighborhood into a queryable Graph RAG store and a Karpathy-style llm-wiki, then teaches Claude — through skills and MCP tools — which lever to pull for which sub-task.

A single command turns one arXiv ID into ~250 papers, ~150 implementation atoms, ~6,000 indexed prose chunks, three detected research communities, and a regenerable wiki — all sitting in `research/` next to your code, addressable by stable IDs, served read-only over MCP.

---

## The hypothesis

PaperBench (2025) measured what we already suspected: frontier models reproduce papers at ~21%, and the dominant failure mode is *missing implementation context* — the kind of detail that lives one citation hop away. Existing paper-to-code systems start from the target PDF and ignore that neighborhood. We compile it.

The thesis being tested, in three operational conditions:

| Condition   | Setup                                        | Predicted outcome                                                                                                  |
| ----------- | -------------------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| **A** | Claude Code + target paper PDF               | baseline                                                                                                           |
| **B** | Claude Code + compiled `research.md` brief | most of the lift                                                                                                   |
| **C** | Claude Code + brief + Graph RAG MCP + wiki   | **+10pp over A**, hallucination halved, atom coverage ≥1.5×, last 3-5pp of accuracy on cross-paper queries |

The plugin succeeds or fails as that research claim. The evaluation rubric lives in `docs/05-evaluation-plan.md`.

---

## What this adds to Claude Code

Three primitives — **skills**, **MCP server**, **forked subagent** — composed into a single plugin so the workflow is one prompt away.

```
┌────────────────────────────────────────────────────────────────────┐
│                  Claude Code session (user-facing)                 │
│   /paper-compiler:build-research-context arxiv:2603.19312          │
│   /paper-compiler:use-research-context     (auto-invoke)           │
│   /paper-compiler:audit-against-research   (auto-invoke)           │
│   /paper-compiler:wiki-query / wiki-ingest / wiki-lint             │
│   15 mcp__paper-compiler__* tools                                  │
└─────────┬──────────────────────────────────────────▲───────────────┘
          │ queries                                  │ structured evidence
          ▼                                          │
┌────────────────────────────────────────────────────────────────────┐
│            paper-compiler MCP server  (read-only)                  │
│  sqlite + sqlite-vec + FTS5; lazy-loaded; ~26 MB per paper         │
└─────────┬──────────────────────────────────────────────────────────┘
          │                                                          
          ▼                                                          
┌────────────────────────────────────────────────────────────────────┐
│              research/  (lives in your repo, git-friendly)         │
│   research.md       — ≤ 8000-token brief                           │
│   research.db       — Graph RAG store                              │
│   SCHEMA.md         — DB schema reference for Claude               │
│   evidence/<atom>.md — per-atom verbatim spans                     │
│   wiki/             — Karpathy llm-wiki (atoms, papers,            │
│                       communities, promoted answers, log)          │
└─────────▲──────────────────────────────────────────────────────────┘
          │ writes (compile-time only)                              
          │                                                          
┌────────────────────────────────────────────────────────────────────┐
│       paper-compiler CLI  — runs once, in a forked subagent        │
│   resolve → acquire → parse → expand → classify → atom-extract →   │
│   score → render → build DB → communities → wiki                   │
└────────────────────────────────────────────────────────────────────┘
```

The strict separation is the point. The CLI **never** serves runtime queries; the MCP server **never** writes. A stale DB diagnosed without re-running a compile. A buggy tool replaced without re-acquiring papers. The wiki regenerated as a pure function of the DB.

---

## What it does well (and the tasks it actually simplifies)

**Implementing a paper from scratch.** Ask Claude `implement the CEM planner from this paper`. The `use-research-context` skill auto-activates, consults its `references/implementing-loss.md` playbook, calls `trace_dependency("optimizer")`, pulls evidence, queries the defining paper's full text, writes the planner with `[[atom-013|CEM]]` citations grounded in verbatim spans. No web search, no hallucinated hyperparameters.

**Cross-paper questions the PDF won't answer.** `/paper-compiler:wiki-query What's the relationship between SIGReg and InfoNCE in this corpus?` — `wiki-query` hits atom search, walks the citation subgraph, pulls chunks from multiple papers, synthesizes a 2-8 paragraph answer, and *promotes* it to `wiki/answers/<slug>.md` if it cites ≥ 2 atoms across ≥ 2 communities. The next session inherits the prior session's reasoning instead of re-discovering it.

**Auditing your implementation against the paper.** `/paper-compiler:audit-against-research` walks every atom that maps to your code and produces a per-atom verdict with citations. PR review for paper reproductions.

**Growing the corpus during use.** `/paper-compiler:wiki-ingest arxiv:2305.18290` adds one more paper (1-5 min), recomputes communities, refreshes wiki articles, appends to `wiki/log.md`. The plugin's knowledge base grows alongside the implementation work.

**Resumability.** Every CLI stage is content-addressed and cached. Rerunning a compile after a parser fix doesn't re-acquire papers; it re-parses and rebuilds from the cache.

---

## How it cuts token usage

The system is built to *replace* web search for paper-specific facts.

| Mechanism                           | Effect                                                                                                                                                       |
| ----------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Snippet-first MCP tools**   | `query_chunks` and `paper_text` return 240-char previews + `chunk_id`. Full text requires `full=True`.                                               |
| **Quality-filtered indexing** | Only ~40% of chunks (the prose ones — tables, captions, layout, references list are excluded) participate in FTS5/vec search.                               |
| **Per-paper diversification** | `max_per_paper=2` stops one mega-paper from crowding out the neighborhood in a single result set.                                                          |
| **Per-skill `references/`** | Heavy task-specific guidance lives in `references/<task>.md`, loaded only when the skill body explicitly points to it. Skill bodies stay ≤ 100-150 lines. |
| **Compile-time LLM caps**     | `--classifier-llm-calls` and `--atom-llm-calls` bound the LLM cost of *building* the store; runtime queries cost only the MCP-result tokens.           |
| **Wiki promotion**            | Synthesized cross-paper answers become addressable files. Future sessions `Read()` an answer instead of re-running the synthesis.                          |

Empirically on the JEPA build: a five-turn implementation session — *plan → implement CEM → implement loss → audit → wiki-query on a subtlety* — consumes ~25K MCP-result tokens. The equivalent web-search workflow, where the agent re-reads the PDF every turn, runs **~6×** that.

---

## What a compile actually produces

Verified on `arxiv:2603.19312` (LeWorldModel/JEPA), 2026-05-18:

| Artifact                        | Result                                                                                                                        |
| ------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| Wall time                       | 1052 s (~18 min)                                                                                                              |
| References attempted / resolved | 52 / 29 (55.8%)                                                                                                               |
| Neighborhood                    | **256 papers** (134 acquired + parsed, 122 metadata-only)                                                               |
| Chunks                          | 14,228 total →**5,672 indexed** (quality filter dropped 60%)                                                           |
| Atoms (post-dedup)              | **153**, across 9 categories, defined by 14 distinct papers                                                             |
| Edges classified                | 42 (8 LLM, 34 heuristic)                                                                                                      |
| Communities detected            | **3** — "JEPA World Models" (22 papers), "Visual World Models Planning" (4), "Graph-Based Adaptive Robot Dynamics" (3) |
| Wiki articles                   | **433** (152 atoms + 256 papers + 3 communities + index + SCHEMA + log + 19 evidence files)                             |
| DB size on disk                 | 28.9 MB                                                                                                                       |
| LLM backend                     | `claude_cli` (no API key; used the Claude Code subscription auth)                                                           |

---

## The MCP surface (15 tools, grouped)

```
paper_summary            citation_neighbors
find_atom                get_evidence            compare_methods
trace_dependency         equation_lookup         (stub — see Limitations)
query_chunks             paper_text              ← hybrid BM25 + vec, snippet-first
neighborhood_subgraph    shortest_path           ← Graph traversal over papers + atoms
list_communities         community_summary
list_missing_details     graph_stats             schema_doc            graph_sql (read-only escape hatch)
```

Hybrid retrieval = FTS5 over chunk text + sqlite-vec KNN on `bge-small` 384-dim embeddings, merged with a quality prior, diversified per paper. The escape hatch (`graph_sql`) accepts arbitrary `SELECT`/`WITH` for when the structured tools don't fit.

---

## Quick start

```bash
# Install
pip install -e plugin-scaffold/cli[graph,indexes] \
            -e plugin-scaffold/server[vector]

# Persist your Semantic Scholar key
echo 'SEMANTIC_SCHOLAR_API_KEY=s2k-...' >> .env

# Launch Claude Code with the plugin
mkdir -p ~/work/paper-impl && cd ~/work/paper-impl && git init
claude --plugin-dir /path/to/plugin-scaffold
```

Inside Claude Code:

```
/paper-compiler:build-research-context arxiv:2603.19312
```

5-20 minutes in a forked subagent. Then ask Claude to implement, audit, or query — `use-research-context` and `audit-against-research` auto-activate when `research/` exists.

For the full pipeline walkthrough, see [`docs/v1_build.md`](docs/v1_build.md) — the single source of truth for what's implemented and how it behaves at every stage.

---

## Repository layout

```
research-compiler/
├── README.md                       ← you are here
├── docs/
│   ├── 01-PRD.md                   product requirements + 11-role label set
│   ├── 02-research-context.md      prior work, reading order
│   ├── 03-claude-code-plugin-guide.md
│   ├── 04-architecture.md          three-plane system design
│   ├── 05-evaluation-plan.md       A/B/C protocol
│   └── v1_build.md                 implementation reference, 1100+ lines
└── plugin-scaffold/                the actual plugin
    ├── .claude-plugin/{plugin.json, marketplace.json}
    ├── .mcp.json
    ├── cli/                        9-stage compilation pipeline
    ├── server/                     read-only MCP server (FastMCP)
    ├── skills/                     6 skills with references/
    ├── hooks/                      warn-only assumption hook
    └── scripts/
```

---

## Current limitations — open for collaboration

The honest list. These are the places the design hits its edges; each is something I'd like to work on with anyone who cares about it.

**Stability**

- **Atom-id reshuffle on recompile.** Sequential `atom-001..NNN` ids are reassigned every compile. Wiki answers that cite `atom-013` may end up pointing somewhere else after the next build. **v0.3 blocker.** Fix is deterministic ids derived from `(category, canonical_name)`.
- **Wiki articles regenerated wholesale.** Hand-edits to generated articles (`atoms/`, `papers/`, `communities/`) are lost. Only `answers/` survives. Intentional, but surprising — worth a non-destructive editing mode.

**Coverage**

- **Reference resolution lands at 45-65%.** The unresolved tail is workshop papers, software releases, technical reports — sometimes implementation-critical. Improvements: batched S2 calls (currently per-reference), better disambiguation on same-title hits, optional Crossref fallback.
- **Tables and figure contents are stripped.** Ablation tables with hyperparameter comparisons carry real signal but die at the digit-ratio rule. Right fix is per-table classification, not blanket exclusion.
- **No OCR on diagrams.** Architecture diagrams that explain layer wiring are invisible.

**Accuracy**

- **Edge classifier ~72% per-role on a 100-edge dev sample** (target was 75%). Heuristic is confident-wrong sometimes; the LLM residual only fires when heuristic confidence is *low*, so it never sees the confidently-wrong cases.
- **Atom extraction is bimodal.** Clean method paragraphs nail it; short or notation-heavy paragraphs return 0-1 atoms.
- **Multi-paper atom extraction skews the distribution** toward citation-rich subfields. A JEPA paper citing 10 robotics papers ends up with robotics atoms dominating. Tunable via `--atom-papers N`, not eliminated.

**Communities**

- **Louvain resolution = 1.4 is a magic number** that worked on JEPA. Other corpora may want 1.0 or 2.0. No auto-tuning yet.
- **Wholesale recompute on every ingest.** Fine for ≤ 500 papers; needs delta updates beyond that.

**Wiki / lint**

- **`wiki-lint` is structural only** (broken wikilinks, orphans, log size). It does *not* catch semantic contradictions across papers or answers. The v2 plan is an LLM-driven semantic lint.
- **No HTML wiki viewer.** Obsidian works today (the wikilink syntax matches) but isn't shippable as part of the plugin.

**MCP server**

- **`equation_lookup` is a stub.** The `equations` table is populated; the client isn't wired. Cheap to fix.
- **Cold start ~1.5 s** (bge-small load). Held in module state after, but the first call pays the cost.
- **`graph_sql` SELECT/WITH check is prefix-based.** Safe locally; not network-safe.

**CLI**

- **`paper-compiler cache prune` is a stub.** Cache grows monotonically — 50-200 MB per compiled paper.
- **Single S2 key.** No rotation.

**Evaluation**

- **The 60-run PaperBench study from `docs/05` hasn't been run yet.** The hypothesis sits unproven. This is the highest-impact open work: pick the held-out paper set, run all three conditions, score with the rubric.

If any of these resonate, open an issue or get in touch (parijat690@gmail.com). The fastest things to land are: stable atom ids, equation tool wiring, `cache prune`, and a Crossref fallback for reference resolution. The most ambitious is the evaluation harness.

---

## Five design decisions baked in (push back here, not at code review)

1. **Plugin, not a standalone CLI.** The packaging *is* the product. PaperBench showed that asking users to glue a workflow together is the failure mode.
2. **Local parsed text is the source of truth; Semantic Scholar is the resolver.** Keeps the system honest about evidence and gives a path to offline / high-volume use.
3. **Implementation atoms as first-class graph nodes.** Not papers, not citations alone. This is where most of the contribution lives.
4. **Compile-time vs. query-time separation.** Heavy work runs once in a forked subagent. The MCP server is read-only at runtime. Anything that blurs this boundary is a bug.
5. **Evaluate against a held-out paper set with a PaperBench-style rubric.** Succeeds or fails as a research claim, not a polished tool.

---

## Pointers

- Implementation reference: [`docs/v1_build.md`](docs/v1_build.md)
- Product requirements + 11-role label set: [`docs/01-PRD.md`](docs/01-PRD.md)
- Three-plane architecture: [`docs/04-architecture.md`](docs/04-architecture.md)
- Evaluation protocol: [`docs/05-evaluation-plan.md`](docs/05-evaluation-plan.md)
- Karpathy's llm-wiki gist (the wiki design ancestor): https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f
