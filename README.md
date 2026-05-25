# research-compiler

> A research paper is a compressed implementation artifact. The detail a coding agent needs to actually reproduce it lives *across the citation neighborhood* — in the cited methods, datasets, baselines, prior architectures, evaluation protocols. **research-compiler** is a Claude Code plugin that compiles that neighborhood into a queryable Graph RAG store and a Karpathy-style llm-wiki, then teaches Claude — through skills and MCP tools — which lever to pull for which sub-task.

A single command turns one arXiv ID into ~430 papers, ~165 implementation atoms, ~19,000 indexed chunks (prose, tables, captions, equations), three detected research communities, and a regenerable wiki — all sitting in `research/` next to your code, addressable by stable UIDs, served read-only over 26 MCP tools.

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
│  sqlite + sqlite-vec + FTS5; lazy-loaded; ~72 MB per paper         │
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
│       paper-compiler CLI  — runs in background, progress monitored  │
│   resolve → acquire → parse → expand → classify → atom-extract →   │
│   score → render → build DB → communities → wiki                   │
└────────────────────────────────────────────────────────────────────┘
```

The strict separation is the point. The CLI **never** serves runtime queries; the MCP server **never** writes. A stale DB diagnosed without re-running a compile. A buggy tool replaced without re-acquiring papers. The wiki regenerated as a pure function of the DB.

---

## What it does well (and the tasks it actually simplifies)

**Implementing a paper from scratch.** Ask Claude `implement the CEM planner from this paper`. The `use-research-context` skill auto-activates, dispatches to the right `implement-<category>` sub-skill, calls `trace_dependency("optimizer")`, pulls evidence, queries the defining paper's full text, writes the planner with `[[atom_uid|CEM]]` citations grounded in verbatim spans. No web search, no hallucinated hyperparameters.

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
| **Chunk taxonomy, not hard exclusion** | Phase 6 indexes every chunk. Retrieval filters on `chunk_kind` (`prose \| table \| caption \| equation_block \| answer`) with per-kind quality floors, so tables and captions surface only when their score beats the floor — not on every query. |
| **Community-scoped routing**  | The `query` tool runs `route_query` (regex, no LLM) then boosts chunks from the top-3 semantically matching communities, pruning the retrieval space before BM25. |
| **Per-paper diversification** | `max_per_paper=2` stops one mega-paper from crowding out the neighborhood in a single result set.                                                          |
| **Tight per-sub-skill tool whitelists** | Each of the 14 `implement-*` / `audit-*` sub-skills declares an `allowed-tools` list of 4–6 MCP tools. The sub-skill context only loads what its category needs. |
| **Compile-time LLM caps**     | `--classifier-llm-calls` and `--atom-llm-calls` bound the LLM cost of *building* the store; runtime queries cost only the MCP-result tokens.           |
| **Wiki promotion**            | Synthesized cross-paper answers become addressable files. Future sessions `Read()` an answer instead of re-running the synthesis.                          |

Empirically on the JEPA build: a five-turn implementation session — *plan → implement CEM → implement loss → audit → wiki-query on a subtlety* — consumes ~25K MCP-result tokens. The equivalent web-search workflow, where the agent re-reads the PDF every turn, runs **~6×** that.

---

## What a compile actually produces

Verified on `arxiv:2603.19312` (LeWorldModel/JEPA), v2.1 build:

| Artifact                        | v1 result | v2.1 result                                                                                          |
| ------------------------------- | --------- | ---------------------------------------------------------------------------------------------------- |
| Wall time                       | 1052 s    | **1180 s** (~20 min)                                                                                 |
| References attempted / resolved | 52 / 29 (55.8%) | 52 / 31 (59.6%)                                                                               |
| Neighborhood                    | 256 papers | **434 papers** (200+ acquired + parsed, rest metadata-only)                                         |
| Acquisition sources             | 1 (arxiv) | **4** — arxiv_tex: 143, s2: 32, openalex: 18, unpaywall: 7                                          |
| Chunks total / indexed          | 14,228 / 5,672 (40%) | **19,500 / 19,500 (100%)** — Phase 6 indexes everything, retrieval filters by `chunk_kind` |
| Atoms (post-dedup)              | 153       | **165**, across 9 categories, defined by 22 distinct papers                                          |
| Edges classified                | 42        | 42 (8 LLM, 34 heuristic)                                                                             |
| Communities detected            | 3         | **3** — "JEPA World Models" (22 papers), "Visual World Models Planning" (4), "Graph-Based Adaptive Robot Dynamics" (3) |
| Wiki articles                   | 433       | **~500**                                                                                             |
| DB size on disk                 | 28.9 MB   | **~72 MB** (2.5× — all chunks indexed + community embeddings)                                       |
| LLM calls per compile           | ~50       | **~95** (Phase 5 budget allocator covers all parsed papers)                                          |
| MCP tools exposed               | 15        | **26**                                                                                               |
| LLM backend                     | `claude_cli` | `claude_cli` (no API key; used the Claude Code subscription auth)                                |

---

## The MCP surface (26 tools, grouped)

```
── Paper lookup ──────────────────────────────────────────────────────
paper_summary            citation_neighbors       get_paper_context
find_atom                get_evidence             compare_methods
trace_dependency         equation_lookup

── Retrieval ─────────────────────────────────────────────────────────
query_chunks             paper_text               query
route_query_only         ← hybrid BM25 + vec + community boost, snippet-first

── Graph traversal ───────────────────────────────────────────────────
neighborhood_subgraph    shortest_path

── Communities ───────────────────────────────────────────────────────
list_communities         community_summary

── Memory plane (ask-gated writes) ───────────────────────────────────
list_sessions            resume_session           get_decisions_since
record_decision          append_session_note      bind_research_dir

── Corpus metadata ───────────────────────────────────────────────────
list_missing_details     graph_stats              schema_doc
graph_sql                ← read-only escape hatch (SELECT/WITH only)
```

Hybrid retrieval = FTS5 over chunk text + sqlite-vec KNN on `bge-small` 384-dim embeddings, merged with a quality prior and community boost, diversified per paper. `query` (auto-routed) is the recommended entry point; `query_chunks` is the lower-level call. `graph_sql` accepts arbitrary `SELECT`/`WITH` for when the structured tools don't fit.

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

5–20 minutes. The build runs as a background process; progress streams in real time via Monitor (expand / classify / dedup / embeddings milestones). MCP tools activate automatically via `bind_research_dir` when the build completes — no session restart needed. Then ask Claude to implement, audit, or query — `use-research-context` and `audit-against-research` auto-activate when `research/` exists.

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
│   ├── v1_build.md                 v1 implementation reference, 1100+ lines
│   ├── v2_build.md                 v2/v2.1 delta over v1 (section numbers aligned)
│   └── v1_v2_delta_chokepoints.md  47+ known issues, severity-tagged, v3 roadmap
└── plugin-scaffold/                the actual plugin
    ├── .claude-plugin/plugin.json  8 slash commands + hooks + mcpServers
    ├── .mcp.json
    ├── cli/                        9-stage compilation pipeline
    ├── server/                     read-only MCP server (FastMCP, 26 tools)
    ├── skills/                     24 SKILL.md files (6 parents + 14 sub-skills + 4 top-level)
    ├── hooks/hooks.json            5 hook types (SessionStart/UserPromptSubmit/PreToolUse/PostToolUse/Stop)
    └── scripts/                    10 bash scripts driving hook lifecycle + build gates
```

---

## Current limitations — open for collaboration

The honest list. Fixed items from v1 are marked ✅. See `docs/v1_v2_delta_chokepoints.md` for the full severity-tagged catalog and v3 roadmap.

**Stability**

- ✅ **Atom-id reshuffle on recompile** — fixed in v2. Stable `atom_uid` (16-hex sha1 of category + canonical_name + defining_paper_id) is now the durable join key. Use `atom_uid` in `decisions.md`, session notes, and code comments; `atom_id` is still sequential but only for human-readable filenames.
- **Wiki articles regenerated wholesale.** Hand-edits to generated articles (`atoms/`, `papers/`, `communities/`) are lost across compiles. Only `wiki/answers/` survives. Intentional, but surprising.
- **Memory plane has no GC.** `decisions.md` grows forever; `sessions/` accumulates one file per session. Manual triage required at scale.

**Build performance**

- **OCR stall on non-ML corpora.** Docling invokes RapidOCR for any PDF page without a native text layer. Physics, chemistry, and older journal papers routinely trigger this — observed 30–60 min builds on a 200-paper neighborhood. Workaround: reduce `--max-papers`; real fix is pre-screening PDFs for text-layer presence before passing to Docling.
- **`SEMANTIC_SCHOLAR_API_KEY` is effectively required.** Without it, builds are rate-limited to 1 RPS (7–10 min of pure API wait for a 200-paper compile). With a free API key, the same wait is ~1 min. The key is free at semanticscholar.org.

**Coverage**

- **Reference resolution lands at 45–65%.** The unresolved tail is workshop papers, software releases, technical reports. Phase 3's multi-source acquisition helps with *fetching* resolved papers but not with *resolving* unmatched bib entries.
- ✅ **Tables and figure captions are indexed** — Phase 6 indexes every chunk with a `chunk_kind` taxonomy. Tables and captions surface when their BM25/dense score beats a per-kind quality floor.
- **No OCR on diagrams.** Architecture diagrams that encode layer wiring are invisible to atoms, chunks, and retrieval.

**Retrieval quality**

- **Chunking truncates mid-sentence.** `split_with_overlap` carries overlap as a raw 200-char character tail — the prefix of every non-first chunk starts mid-word or mid-sentence, degrading embedding quality. The sentence splitter also only handles `.!?`, missing `:`, `;`, `\n\n`, and theorem/proof terminators common in physics/math papers.
- **No token-budget check.** Chunk sizing uses character counts; a LaTeX-heavy paragraph at 750 chars can exceed bge-small's 512-token encoder limit and get silently truncated. `tiktoken` is already a dependency and would give an accurate count.
- **`bge-small-en-v1.5` is English-only and domain-general.** Non-English papers in the neighborhood get poor embeddings; highly technical vocabulary (Riemann solvers, Godunov schemes) maps poorly in a general-purpose 384-dim space. `specter2` (scientific BERT) or `bge-base` are better choices for non-ML corpora but aren't configurable today.

**Accuracy**

- **Edge classifier ~78% per-role** on a 100-edge JEPA dev sample (above the 75% target). Heuristic is confident-wrong sometimes; the LLM residual only fires on *low*-confidence heuristic outputs, never on confidently-wrong ones.
- **Atom extraction is bimodal.** Clean method paragraphs produce good atoms; short or notation-heavy paragraphs return 0–1 atoms at full LLM cost.

**Communities**

- **Louvain resolution = 1.4 is a magic number** verified only on JEPA. Other corpora may need different values. Edit `communities.py:121` directly to tune.
- **Wholesale recompute on every ingest.** Fine for ≤ 500 papers; needs delta updates beyond that.

**Wiki / lint**

- **`wiki-lint` is structural only** (broken wikilinks, orphans, log size). Semantic contradictions across papers or across `decisions.md` entries are not detected.
- **No HTML wiki viewer.** Obsidian works today (wikilink syntax matches) but isn't shippable as part of the plugin.

**MCP server**

- ✅ **`equation_lookup`** — no longer a stub. Phase 6 populates `chunks_vec` for `chunk_kind='equation_block'` rows; equations are retrievable.
- **`sqlite-vec` silently disabled** when `enable_load_extension` is blocked (system Python on macOS, some conda envs). Fallback to FTS5-only with no warning — vector retrieval is simply missing.
- **Cold start ~1.5 s** (bge-small load). Held in module state after.
- **`graph_sql` SELECT/WITH check is prefix-based.** Safe locally; not network-safe.

**CLI**

- **`paper-compiler cache prune` is a stub.** Cache grows monotonically — 50–200 MB per compiled paper.
- **Single S2 key.** No key rotation for concurrent compiles.

**Evaluation**

- **The PaperBench study from `docs/05` hasn't been run.** The hypothesis (Condition C beats A by ≥10pp) is unproven. This is the highest-impact open work.
- **Domain neutrality is asserted, not verified.** The plugin is described as domain-neutral (ML, physics, chemistry, biology) but has only been validated on ML papers. The physic-simulo build (arxiv:2602.00658) is the first non-ML test, currently in progress.

If any of these resonate, open an issue or get in touch (parijat690@gmail.com). High-leverage near-term targets: OCR pre-screening, token-budget chunking, sentence-boundary-aware overlap, and the PaperBench evaluation harness.

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
