# v2 Build — paper-compiler End-to-End

**Status:** v2.1 (post-Phases 1–8 + Claude Code integration layer A–F + v2.1 monitoring fixes)
**Schema version:** `2.0` (bumped in `graph_db.py:57`)
**Companion to:** `docs/v1_build.md`, `docs/01-PRD.md`, `04-architecture.md`, `05-evaluation-plan.md`

This document is the delta over `v1_build.md`. It keeps v1's section numbering so a reader can hold both open side by side. Each section is structured as:

> **What changed** — concrete code/contract delta.
> **Improvement observed** — what got better and by how much (where measured).
> **Chokepoints / bottlenecks** — what is still wrong or now wrong in a new way.

Sections without a delta are noted as "unchanged from v1" so the numbering stays aligned.

---

## v2.1 patch notes

**`build-research-context` skill — monitoring architecture.** Removed `context: fork` and `disable-model-invocation: true`. Build now starts via Bash `run_in_background: true`, output piped to `/tmp/paper-compiler-<paper-id>.log`. The skill uses the Monitor tool to stream progress lines (`expand:`, `classify:`, `dedup:`, `embeddings:`) to the main session in real time — previously the main session saw nothing until the 5–20 min subagent returned. After the background process exits, `mcp__paper-compiler__bind_research_dir` is called automatically so all 26 MCP tools are live without a session restart. The `--out` path is now the absolute `${CLAUDE_PROJECT_DIR}/research` (was the relative `research/`, which was CWD-dependent inside the forked subagent).

**`stop.sh` + `session-start.sh` — directory boundary escape.** `find_research_dir()` in both scripts fell through to a cwd walk-up when `CLAUDE_PROJECT_DIR` was set but `build-manifest.json` didn't yet exist (first build in a fresh consumer repo). If the walk-up reached a parent directory containing a different `research/` (e.g. the research-compiler repo's own compiled research), the hooks injected the wrong paper's context and wrote session notes to the wrong directory. Fix: when `CLAUDE_PROJECT_DIR` is set, return 1 immediately on manifest-not-found; never walk outside the declared project boundary.

**`stop.sh` — printf crash.** `decisions_made="$(grep -c ... 2>/dev/null || echo 0)"` produced the two-line string `"0\n0"` on macOS: `grep -c` exits 1 on no matches but still prints `0`, so the `|| echo 0` fallback appended a second line. `printf %d "0\n0"` then crashed with `printf: 0\n0: invalid number`. Fixed with `|| true` and a `${:-0}` default on the next line. Same pattern fixed in `session-start.sh` for `decisions_count`.

---

## 1. Hypothesis

**What changed.** The compressed claim is unchanged — papers are compressed implementation artifacts; detail lives in the neighborhood; a Claude Code plugin with Graph RAG + MCP + skills outperforms web search. v2 widens scope: the plugin is now declared **domain-neutral** in `plugin.json` ("ML, physics, chemistry, biology, economics, climate"). The 11-role ML-flavoured edge set is supplemented with a domain-agnostic vocabulary in the LLM classifier prompt, and atom categories collapse to the domain-neutral set (`method`, `objective`, `data`, `procedure`, `evaluation`, `baseline`, `theory`) surfaced through sub-skill names.

The tertiary claim about session-to-session memory is now a **first-class plane** rather than an emergent property of `wiki/answers/` (see §4 and §17).

**Improvement.** Same condition A/B/C structure; the gap-closing prediction for C now also covers cross-session work (a session that resumes prior work avoids re-deriving atoms).

**Chokepoint.** PaperBench-style evaluation (§15 item 11 in v1) is still not run. Domain coverage outside ML is asserted in `plugin.json` but not verified on a non-ML build.

---

## 2. System overview

**What changed.** The three-plane model survives intact for the *structured* artifact (CLI writes; MCP reads). A **fourth plane** lands alongside it:

```
research/                        ← structured (CLI-write, MCP-read)
  research.db | graph.json | wiki/ | evidence/ | embeddings.* | SCHEMA.md | research.md
research/                        ← memory (human-write, MCP-read + write-via-tool)
  CLAUDE-PAPER-CONTEXT.md        per-paper context fragment (CLI-emitted on every compile)
  decisions.md                   append-only structured gotchas log
  sessions/<date>-<slug>.md      one note per Claude Code session
```

`record_decision` and `append_session_note` MCP tools are the *only* server-side writers, both ask-gated in `settings.json` permissions. The original "MCP never writes" invariant is now scoped to **structured artifacts** — markdown memory is an additive plane with a narrower write surface.

The three-plane diagram in v1 §2 gains a fifth lifecycle component: **hook-driven I/O** (SessionStart injects context, UserPromptSubmit routes intent, PostToolUse appends events to `wiki/log.md`, Stop writes a session note).

**Improvement.** Cold-session continuity. A new session opens with the per-paper context already in the system prompt (`CLAUDE-PAPER-CONTEXT.md`, ~40 lines of routing hints + category counts + source coverage), so the first user turn doesn't waste tokens re-discovering the brief.

**Chokepoint.** The memory plane has no garbage collection. `decisions.md` grows forever; `sessions/` accumulates one file per session. The Stop hook deduplicates within a session but not across them. At the JEPA build's current cadence (~5 sessions/week) this is fine for a year; beyond that, expect manual triage.

---

## 3. The CLI compile pipeline

Stage count unchanged (nine), but most stages have shifted. Cache layout at `~/.cache/paper-compiler/` is unchanged and still content-addressed.

### 3.1 Stage 1 — Resolve

Unchanged. `resolve.py` semantics are the same; DOI parsing is still regex-based; the `confidence < 0.9` gate is still advisory.

### 3.2 Stage 2 — Acquire — **rewritten** (Phase 3)

**What changed.** v1's hard-coded `arxiv → S2 openAccessPdf → local PDF` chain is replaced by a configurable multi-source pipeline (`acquire.py`, `SourcesConfig`). Trial order (default) is:

```
arxiv → s2 → openalex → unpaywall → crossref
```

First success wins; the winning source's name is recorded into `papers.acquired_via` (new column) and aggregated in `build-manifest.json::papers_by_source`. The "polite pool" identifier (`contact_email`) is shared across OpenAlex (`mailto=`), Unpaywall (`email=`, required), and Crossref (User-Agent). Per-source rate limits default to 2 RPS.

**Improvement.** Coverage. v1 routinely lost 3% of papers to HTTP failures on the arXiv e-print mirror plus everything not on arXiv. v2 picks those up via OpenAlex / Unpaywall — on a 200-paper neighborhood that's typically 5–15 additional acquisitions, lifting the parsed-paper count by 3–8%. The HTML-as-PDF false-positive bug is still present but no longer load-bearing because alternate sources cover the same paper.

**Chokepoint.** Three new ones.

- **No source-quality preference.** Unpaywall can serve a publisher-rendered PDF for a paper that also has arXiv TeX; we take whichever came first in the chain. Should prefer TeX for parsing fidelity even at the cost of latency.
- **Polite pool identifier is mandatory** on Unpaywall and silently degrades S2 throughput when missing. `setup.sh` writes a default but the user has to override it.
- **Crossref** rarely yields full text — it's mostly a metadata source. Keeping it last is correct, but it still consumes a request slot.

### 3.3 Stage 3 — Parse to IR — **Docling default** (Phase 3 cont.)

**What changed.** `parse/pdf.py` ships two backends:

- **`docling`** (default, v2.0): IBM's structured PDF parser. Walks `DoclingDocument.iterate_items()`, so headings, tables, equations and captions arrive as structured items rather than reconstructed regex matches.
- **`marker`** (legacy, deprecated v1.0): rendered-markdown + regex walker. Kept behind `parser.pdf_backend = "marker"` for one release with a stderr deprecation warning.

`ParserConfig.pdf_backend` default flipped from `"marker"` to `"docling"` in `config.py:65`. TeX path is unchanged (still preferred when available).

**Improvement.** Docling is ~10× faster on a typical 30-page PDF (no 3 GB checkpoint, no torch dependency for the basic install) and yields structured `TableItem` + `EquationItem` records that we surface as proper `equations` / table-caption chunks. Captions are now reliably attributed to the figure they describe, not glued to the next paragraph.

**Chokepoint.**

- **Docling still loses heavy macro semantics** when handed a PDF that originated from TeX — equations come through as LaTeX but algorithm boxes do not.
- **Figure body OCR** is still absent. Diagram-encoded architecture details remain invisible.
- The **TeX walker** is unchanged — heavy macro rebinding in NeurIPS templates still truncates parses. Listed in v1 §3.3, still listed here.

### 3.4 Stage 4 — Expand neighborhood — **minor**

**What changed.** Expansion logic is unchanged (two-pass: reference resolution then frontier expansion with priority scoring). Two adjustments:

1. The `--atom-papers N` cap (v1's "extract atoms from top-N cited papers") was **removed**. Phase 5's budget allocator (see §3.6) consumes all parsed papers proportional to incoming edge weight, so the discrete top-K knob no longer has a consumer. Existing `paper-compiler.toml` files that still set it are silently ignored by `config.py::_merge` (only recognized fields land).
2. Reference resolution now batches more aggressively (50% fewer S2 calls on JEPA: 27 vs ~55 in v1) but the batch endpoint is still not used for the *initial* fan-out — only metadata enrichment.

**Improvement.** Lower S2 cost per compile + atom extraction now reaches papers that were below v1's top-10 cutoff but high in edge weight (e.g. a single dataset paper cited only twice but in two method paragraphs).

**Chokepoint.** Depth-2 priority inheritance (`0.5 * parent`) is still heuristic and still under-tuned. Same with the 45–65% reference-resolution rate — Phase 3's multi-source change improves *acquisition* coverage, not *resolution* coverage.

### 3.5 Stage 5 — Classify citation edges — **Phase 4 rewrite**

**What changed.** The hybrid heuristic + LLM classifier survives, but the eleven-role set gains a twelfth role: **`contradicts`**. `heuristic.py:25` adds a negation-proximity detector (negation/refutation tokens within ~50 chars of the citation) that hard-boosts the `contradicts` label. The LLM residual pass now emits both a *role* and an *intent* (one of `supports`, `refutes`, `extends`, `uses`, `discusses`), recorded on the edge.

Two new fields on `ClassifiedEdge`:
- `provenance_rule` — the heuristic rule name or `"llm"` that produced the top label. Lets the auditor say "this edge came from the section-prior rule" vs "the LLM relabeled it".
- `source_atom_uids` — atoms in the citing paragraph; used in §3.6 to anchor "this paper uses atom-X via this edge".

**Improvement.** Edge auditability. The dev-sample accuracy bumped from ~72% to ~78% per role (above the 75% target in `docs/05`) once the `contradicts` row started absorbing what was previously mislabeled as `related_work_only`. Intent labels also flow into community-summary prompts, producing labels like "ablations refuted in JEPA follow-ups" rather than "JEPA-related papers".

**Chokepoint.**

- **Confidently-wrong heuristics still escape LLM rescue** — same bug as v1, just smaller in absolute terms.
- `intent` is recorded but **not yet surfaced through any MCP tool** in v2.0. `citation_neighbors` returns role only.
- **Multi-label use** of `edge_roles` is still rare downstream; `best_role` dominates.

### 3.6 Stage 6 — Atom extraction — **Phases 1 + 5 (biggest delta)**

**What changed.** Two structural changes plus several quality fixes.

**Phase 1 — stable atom uids.** `atoms/extract.py:119` introduces `_atom_uid(category, name, defined_by_paper_id)` — a 16-hex `sha1(normalizer_version, canonical_name, defining_paper_id)`. Stored on every atom as `atom_uid TEXT NOT NULL` with `UNIQUE INDEX ix_atoms_uid`. `atom_id` (sequential `atom-NNN`) still exists for human-readable wiki filenames but is **never** the cross-rebuild join key.

This unblocks the v0.3 blocker noted in v1 §3.6 and §14: wiki answers, decision notes, and code comments can now cite `atom_uid` and survive recompiles. Plugin convention (`plugin-scaffold/CLAUDE.md`) explicitly requires `atom_uid` in `decisions.md`, session notes, and code comments — `atom_id` is reserved for in-session reference only.

**Phase 5 — budget-allocator atom extraction.** v1's `_extract_for_paper(paper, …)` called for the target + top-10 cited papers (`atom_paper_count`) is replaced by an edge-weight-proportional allocator over **all** parsed papers in the neighborhood. Every parsed paper gets some LLM-call budget; high-incoming-edge-weight papers get more. The target still has `priority_factor = 1.0` so its atoms remain on top.

**Other deltas:**
- `Atom.subcategory` field added. LLM extractor emits an optional free-text refinement (e.g. category=`objective`, subcategory=`contrastive`); heuristic path leaves it `None`.
- Dedup unchanged in algorithm but now dedupes across all-paper extraction, so JEPA goes from 153 → ~210 atoms (Phase 5's broader extraction) before settling to ~165 post-dedup.

**Improvement.**
- **Cross-rebuild atom references are now safe.** This is the single biggest correctness improvement in v2. Wiki `answers/`, `decisions.md`, and code comments stay valid across compiles.
- **Atom recall on long-tail citations** is up (Phase 5 reaches papers v1 ignored).
- **Subcategory** gives sub-skills a cheap routing key without inventing 30+ top-level categories.

**Chokepoint.**
- **Phase 5 LLM cost.** Every parsed paper now consumes some budget — total LLM calls per compile jumped from ~50 (v1 default) to ~75–110 depending on neighborhood size. Mitigated by `--atom-llm-calls` cap, but the default is unchanged at 80, meaning the cap actually binds in v2 (it rarely did in v1).
- **Bimodal LLM output** (v1 §3.6) is still bimodal. Now it's bimodal across more papers.
- **Junk-name regexes** still mislabel a handful of hyperparameters as full atoms; v1's `_is_junk_name` is unchanged.
- `subcategory` is **never used by retrieval** in v2.0 — only by the LLM community summarizer and the audit sub-skill prompts.

### 3.7 Stage 7 — Score and rank

Unchanged. Weights are still guesses; `dependencies` between atoms is still rarely populated; recency is still under-weighted.

### 3.8 Stage 8 — Build the Graph RAG DB — **Phases 6, 7, 8**

**What changed.** Schema bump to `2.0`. New / changed columns and tables:

```
atoms          + atom_uid TEXT NOT NULL, subcategory TEXT, UNIQUE INDEX ix_atoms_uid
chunks         + chunk_kind TEXT DEFAULT 'prose', INDEX ix_chunks_kind
                 is_indexed kept for one release, defaults to 1 (Phase 6 indexes everything)
edges          + provenance_rule TEXT, source_atom_uids TEXT, intent TEXT
papers         + acquired_via TEXT
communities_vec  (new vec0 table) — 384-dim embeddings of label + summary
```

**Phase 6 — index-everything.** v1 indexed ~40% of chunks (5,672 / 14,228 on JEPA) using `is_indexable()`. v2 indexes **every** chunk; retrieval filters on `chunk_kind` instead. The taxonomy:

```
prose | table | caption | reference | equation_block | answer
```

Default quality floors for non-prose kinds (so they can still surface on high BM25/dense scores): `table=0.55`, `caption=0.45`, `reference=0.30`, `equation_block=0.50`, `answer=0.80`.

**Phase 7 — community-aware routing.** `communities_vec` lets `query_chunks` boost chunks whose `paper_id` belongs to a community that semantically matches the query. The router (§5) decides whether to apply the boost.

**Phase 8 — answer re-embedding.** At compile end, promoted wiki answers (`wiki/answers/*.md`) are re-embedded and inserted as `chunk_kind='answer'` rows, so `query_chunks` retrieves last session's synthesized answers alongside paper text. This was a v2 candidate in v1 §15 item 5.

**Improvement.**
- **Table / caption / equation retrieval.** v1's hard exclusion of tables (digit-ratio rule) is gone. The JEPA ablation table that was unreachable in v1 now retrieves on `query_chunks("ablation hyperparameter values")`.
- **Community boost** lifts mean reciprocal rank on a small dev set of 20 cross-paper queries by ~12% over the v1 hybrid score.
- **Answer reuse.** A second session asking "what did we decide about CEM elite fraction" hits the previous session's promoted answer with no extra calls.

**Chokepoint.**
- **Index size grew ~2.5×.** JEPA DB went from 28.9 MB (v1) to ~72 MB (v2). Chunk embeddings on disk grew from ~9 MB → ~22 MB.
- **Cold-start time** is up: bge-small load is unchanged, but the larger `chunks_vec` table costs ~200 ms more on first KNN.
- **`chunk_kind` is heuristic** (regex over text + section_type). Mis-classifies dense math paragraphs as `equation_block` occasionally.
- **No tier per kind in retrieval.** `query_chunks` defaults still pull from all kinds; the user has to pass `kinds=[...]` to filter — the API exists but isn't auto-used by skills.

### 3.9 Chunking and quality filtering — **superseded** (Phase 6)

**What changed.** `text_utils.is_indexable` is now a one-line stub kept for one release; the real decision is `classify_chunk_kind(section_type, section_title, text, override_kind=None) -> (kind, quality)`. Hard rejects (letter ratio, digit ratio, table-punct ratio) survive only as inputs to `prose_quality`, never as drop conditions.

200-char overlap is unchanged; chunk sizing (`target_chars=750`) is unchanged.

**Improvement.** No more silently-dropped chunks. Anything you can `paper_text(chunk_ids=[N])` can also be retrieved by search if the score is high enough.

**Chokepoint.** Quality floors per kind are guesses, not learned. Long related-work sections still over-chunk; short paragraphs still under-overlap.

### 3.10 Stage 9 — Communities — **embedded** (Phase 7)

**What changed.** Detection algorithm unchanged (Louvain @ resolution 1.4, NetworkX fallback). What's new: every community is embedded (label + summary, bge-small, 384-dim) into `communities_vec`. The router calls `_top_communities(conn, query, k=3)` to pick the relevant clusters before chunk retrieval.

**Improvement.** On the JEPA build, queries about "world models in robotics" now correctly bias toward the "Graph-Based Adaptive Robot Dynamics" community even when the BM25 winners are from "JEPA World Models". The boost is multiplicative on the chunk score for chunks whose paper is in the top-3 communities.

**Chokepoint.** Recompute is still wholesale on every compile/ingest. Resolution 1.4 is still a magic number. Community embedding adds ~12 LLM-summary calls per compile (same cap as v1; unchanged).

### 3.11 Render: research.md + wiki + DB — **plus paper-context fragment**

**What changed.** Render set is unchanged plus:
- `research/CLAUDE-PAPER-CONTEXT.md` — emitted by `render/paper_context.py` on every compile. ~40 lines: title + atom-category counts + source coverage + routing hints + hard rules. Inlined verbatim by the SessionStart hook.
- `decisions.md` is created on first compile with a header but stays otherwise empty.
- `sessions/` directory is created on first compile.

`build-manifest.json` gains `papers_by_source` and `evidence_provenance.{total,chunk_id_resolved,resolved_pct}` to surface the v2 Phase-3 / Phase-1 telemetry.

**Improvement.** The context fragment closes the cold-session gap noted in §2. SessionStart hook fires before any user turn, so the first prompt already routes correctly.

**Chokepoint.** The fragment is regenerated wholesale; user edits are lost. Same hand-edits-lost issue as wiki articles (v1 §4.6).

---

## 4. The wiki — **augmented by memory plane**

**What changed.** Wiki article tree (`atoms/`, `papers/`, `communities/`, `answers/`, `index.md`, `SCHEMA.md`, `log.md`) is unchanged. Three additions live *outside* `wiki/` in the new memory plane:

```
research/decisions.md            append-only structured gotchas
research/sessions/<date>-<slug>.md   per-session note
research/CLAUDE-PAPER-CONTEXT.md     per-paper context fragment
```

Two new MCP write tools (ask-gated): `record_decision(category, decision, why, atom_uid?, source_chunk_id?, source_paper_id?, slug_hint?)` and `append_session_note(note, kind, session_id?)` with kinds `atom_touched | file_modified | decision_referenced | next_step`. The Stop hook auto-calls `append_session_note` at session end; manual calls during the session are for highlighting load-bearing moments only.

Wiki answers carry `atom_uid` references in addition to `atom_id`. The `atom_uid` is the durable cite key.

**Improvement.**
- **Cross-session continuity** is no longer an emergent property of `answers/` — it's a load-bearing plane with two write tools and a hook that exercises them.
- **Decision audit trail.** A reproduction author can now answer "why did we pick CEM iterations = 5?" with a `decisions.md` grep, with chunk-id provenance back to the paper.

**Chokepoint.**
- **No write-back into chunks_fts** for `decisions.md` content — only `wiki/answers/` get re-embedded (Phase 8). A decision rationale is not searchable by `query_chunks` until the next compile promotes a relevant answer.
- **`record_decision` cardinality**. Plugin CLAUDE.md instructs Claude to skip "routine implementation work", but the threshold is fuzzy and over-recording is a known failure mode.
- **`wiki-lint` is still structural-only.** Semantic contradictions across `decisions.md` entries are not detected.

---

## 5. The MCP server — **15 → 26 tools + query router**

**What changed.** Tool surface roughly doubled. Existing tools unchanged in signature except `query_chunks` (gains `kinds: list[str] | None`, `prefer_kind: str | None`, community-boost), `find_atom` (now searches `name + description + subcategory`), and `equation_lookup` (no longer a stub — Phase 6 populates `chunks_vec` for `chunk_kind='equation_block'` rows).

New tools:

| Tool | Purpose |
| --- | --- |
| `get_paper_context()` | Returns the structured equivalent of `CLAUDE-PAPER-CONTEXT.md`. Skills call this instead of `Read`-ing the file. |
| `list_sessions(limit=5)` | Most-recent session notes with date + slug + atom_uid touch count. |
| `resume_session(session_id)` | Atoms touched, files modified, next-steps from one session. |
| `get_decisions_since(since="")` | Decisions newer than the given ISO date, or all decisions if empty. |
| `record_decision(...)` | Append to `decisions.md`. Ask-gated. |
| `append_session_note(...)` | Append to a session file. Ask-gated. |
| `bind_research_dir(path)` | Re-bind `PAPER_COMPILER_RESEARCH_DIR` mid-session (for multi-corpus work). |
| `route_query_only(q)` | Returns `"local" | "global" | "hybrid"` from `route_query()`. Lets a skill see the routing decision without executing it. |
| `query(q, mode="auto", ...)` | One-shot retrieval that runs `route_query` then `query_chunks` with community boost. |

**Query router** (`db.py:156`, `route_query`): cheap, deterministic, no LLM. Regexes over the query string return one of `local | global | hybrid`. Local triggers entity/value patterns (`what is the X`, `value of`, `arxiv:`, `cite[ds]?`). Global triggers comparative/thematic patterns. Hybrid is the fallback. The caller can override with `mode=...`.

**Hard policy enforcement.** v1's `denyTools` lived in `.claude/settings.json`. v2 enforces via `PreToolUse` hook (`scripts/enforce-mcp-access.sh`) so:
- The policy travels with the plugin, not the consumer repo's settings.
- Direct `Read`/`Glob`/`Grep` on `research/wiki/atoms/**`, `research/wiki/papers/**`, `research/wiki/communities/**`, `research/evidence/**`, `research/graph.json`, `research/research.db`, `research/embeddings.{npy,json}` exit with code 2 and a one-line message naming the MCP equivalent.
- `research/research.md`, `research/decisions.md`, `research/sessions/*.md`, `research/CLAUDE-PAPER-CONTEXT.md` remain readable — they're human-meant-to-write markdown.

**Improvement.**
- **Routing wins.** On the same 20-query dev set used in §3.8, `query` (auto-routed) outperforms `query_chunks` (manual) by ~7% MRR — most of the win comes from `global` queries that now retrieve community summaries first.
- **`equation_lookup` works.** The v1 stub is gone; equations are now retrievable as `chunk_kind='equation_block'`.
- **Hook-enforced policy** is more robust than settings-based denials — the user can't accidentally disable it by editing their own `settings.json`.

**Chokepoint.**
- **`graph_sql` prefix check is still prefix-based.** Acceptable locally; not network-safe.
- **`paragraph_ids` filter still un-validated** against the target paper (v1 §5 chokepoint, unchanged).
- **Router rules are tuned for the JEPA audit corpus.** A physics-paper compile asking "what is the value of the coupling constant" routes correctly, but "compare RG flow across these papers" gets `hybrid` instead of `global`.
- **`record_decision` / `append_session_note` permissions** rely on Claude Code's `ask` gate; a user who clicks through gets no rate limit.

---

## 6. LLM backend — **unchanged in shape, larger in volume**

**What changed.** Backend priority is identical: `ANTHROPIC_API_KEY` → `claude -p` headless → none. `call_llm()` entry point unchanged. What's larger: Phase 5 widens atom extraction to all parsed papers, and Phase 4 adds an intent call alongside the role call, so a typical compile draws ~75–110 LLM calls (v1 was ~50). With `claude_cli` backend, this adds ~60–120 s wall time on top of v1's already-noted overhead.

**Improvement.** None on the backend itself.

**Chokepoint.** Cost. The `--classifier-llm-calls` and `--atom-llm-calls` caps now actually bind (in v1 they were headroom).

---

## 7. Skills — **6 → 24 skills (parent + nested)**

**What changed.** Three structural shifts:

**(a) Nested sub-skills.** `use-research-context` and `audit-against-research` are now *parents* that dispatch to category-specific *children* in `skills/<parent>/skills/<child>/SKILL.md`:

```
use-research-context/skills/
  implement-method | implement-objective | implement-data | implement-procedure
  implement-evaluation | implement-baseline | port | continue | debug-divergence

audit-against-research/skills/
  audit-method | audit-objective | audit-data | audit-procedure
  audit-evaluation | audit-baseline | audit-theory
```

Each sub-skill is `context: fork` with a tight `allowed-tools:` whitelist (typically 4–6 MCP tools). v1's `references/*.md` files are **deleted** — task-specific guidance moved into the sub-skill body, which is now the unit of dispatch.

**(b) Two new top-level skills.** `compare-corpora <dirA> <dirB>` (cross-corpus atom/community diff) and `resume-session` (one-shot "what was I doing?" wrapping `list_sessions` + `resume_session` + `get_decisions_since`).

**(c) Routing via UserPromptSubmit hook.** `scripts/detect-intent.sh` greps the user's submitted prompt and emits a one-line suggestion of the right parent skill. The hook is advisory, not mandatory — Claude can override.

Total: 6 parents + 14 sub-skills + 2 new top-level + 2 unchanged (`build-research-context`, `wiki-ingest`) + 2 unchanged (`wiki-query`, `wiki-lint`) = 24 SKILL.md files.

**v2.1 update — `build-research-context`.** Frontmatter changed: `context: fork`, `disable-model-invocation: true`, and `agent: general-purpose` removed. Skill now runs inline in the main session; build starts as a background Bash process writing to a log file; Monitor streams progress; `bind_research_dir` fires on completion. See v2.1 patch notes above for detail.

**Improvement.**
- **Body length tractable.** Each sub-skill body is 60–120 lines, well under Anthropic's 500-line guidance. The parent decides *which* sub-skill to invoke; the sub-skill body has only the routing logic for its category.
- **`context: fork` blast radius**. A sub-skill that goes wrong corrupts only its forked context, not the main session.
- **Intent-detection** removes one round-trip of "which skill should I use?" — the user's prompt arrives with a suggestion.

**Chokepoint.**
- **Sub-skill duplication.** `implement-method` and `audit-method` share ~30% of their MCP call sequences. Not refactored — each lives independently.
- **Hook-based intent detection** is a bash grep, not semantic. "implement the loss" routes to `implement-objective`, but "implement the procedure" can ambiguously route to `implement-procedure` or `port` depending on phrasing.
- **`allowed-tools` whitelist** is verbose to maintain. A new MCP tool requires updating ~10 SKILL files.

---

## 8. CLI surface

**What changed.** Subcommands unchanged. Flag changes:
- `--atom-papers N` **removed** (Phase 5; see §3.4). Silently ignored if set in TOML.
- `--no-llm` still works.
- All other flags unchanged.

`paper-compiler.toml` schema gains `[sources]` block:

```toml
[sources]
enabled = ["arxiv", "s2", "openalex", "unpaywall", "crossref"]
contact_email = "you@example.com"   # required by Unpaywall, polite for S2/OpenAlex/Crossref
rate_limit_rps = 2.0
```

And `[parser]`:

```toml
[parser]
pdf_backend = "docling"   # default flipped from "marker" in v2.0
```

**Improvement.** Multi-source acquisition is now a config-time choice, not a code-edit.

**Chokepoint.** `cache prune` still unimplemented. Multi S2 key support still missing.

---

## 9. Plugin layout

**What changed.** `plugin-scaffold/` gains:

```
scripts/                       (was 1 file, now 10)
  setup.sh                     idempotent project config
  session-start.sh             injects CLAUDE-PAPER-CONTEXT.md
  detect-intent.sh             UserPromptSubmit hook
  enforce-mcp-access.sh        PreToolUse Read/Glob/Grep denial
  check-assumptions.sh         PreToolUse Write/Edit warn (unchanged from v1)
  post-tool.sh                 PostToolUse for decision/ingest events
  stop.sh                      Stop hook writes session note
  validate-build-manifest.sh   gate checker called by build-research-context
  select-playbook.sh           sub-skill picker for use-research-context
  lint-wikilinks.sh            wiki-lint helper
hooks/hooks.json               (5 hook types declared; v1 was warn-only on PreToolUse)
skills/                        (24 SKILL.md, see §7)
```

`.mcp.json` `PAPER_COMPILER_RESEARCH_DIR` now uses `${CLAUDE_PROJECT_DIR}` instead of `${PWD}` (the SessionStart hook walks up from cwd if the MCP server starts before the project dir is known).

`.claude-plugin/marketplace.json` removed (the file lived outside the plugin proper; registration is now via `claude --plugin-dir`).

**Improvement.** All policy enforcement and lifecycle plumbing travels with the plugin. A fresh consumer repo gets correct behavior with zero `.claude/settings.json` edits.

**Chokepoint.** **10 bash scripts is the new attack surface.** Each is exit-code-meaningful (the hook system gates tool calls on exit 2). Bash 3.2 compatibility was specifically fixed in claude-mem `2483` / `2485`; future scripts need the same discipline.

**v2.1 update — `stop.sh` + `session-start.sh`.** Two bugs fixed: (1) `find_research_dir()` boundary escape (see v2.1 patch notes); (2) `grep -c ... || echo 0` printf crash in `stop.sh`. Both scripts hardened.

---

## 10. Build numbers — verified on JEPA (arxiv:2603.19312)

Same target, fresh v2 build (`--refresh`, otherwise default flags):

| Metric | v1 (v0.2) | v2 (v2.0) | Δ |
| --- | --- | --- | --- |
| Wall time | 1052 s | 1180 s | +12% |
| References resolved / attempted | 29 / 52 (55.8%) | 31 / 52 (59.6%) | +3.8 pp |
| Papers in neighborhood | 256 | 434 (Phase 3 reach) | +178 |
| Papers acquired (full text) | 134 | 200+ | +66+ |
| Acquisition sources used | 1 (arxiv) | 4 (arxiv/s2/openalex/unpaywall) | new |
| Chunks total / indexed | 14,228 / 5,672 (40%) | 19,500 / 19,500 (100%) | Phase 6 |
| Atoms (post-dedup) | 153 | 165 | +12 |
| Distinct defining papers | 14 | 22 | +8 |
| Communities | 3 | 3 | unchanged |
| Wiki articles | 433 | ~500 | +67 |
| DB size on disk | 28.9 MB | ~72 MB | 2.5× |
| LLM calls per compile | ~50 | ~95 | +90% |
| MCP tools exposed | 15 | 26 | +11 |

Sources by paper (from `build-manifest.json::papers_by_source` on the v2 build):

```
arxiv_tex      143
s2_openaccess   32
openalex_pdf    18
unpaywall_pdf    7
```

Build gates (`validate-build-manifest.sh`): `papers_in_neighborhood ≥ 5`, `coverage_pct ≥ 50`, `atoms_extracted ≥ 8` — all passing on JEPA with 4 soft warnings (recorded in claude-mem `2518`).

---

## 11. End-to-end usage

**What changed.** Setup steps shortened. The plugin's SessionStart `setup.sh` is idempotent and writes the consumer-repo skeleton (decisions/sessions/CLAUDE-PAPER-CONTEXT shells), so the user no longer hand-creates anything in `research/`.

```bash
mkdir ~/work/paper-impl && cd ~/work/paper-impl && git init
claude --plugin-dir /path/to/research-compiler/plugin-scaffold
# first turn:
/paper-compiler:build-research-context arxiv:2603.19312
```

Subsequent sessions in the same repo open with `CLAUDE-PAPER-CONTEXT.md` already in the system prompt and a fresh `sessions/<date>-<slug>.md` waiting to receive Stop-hook output.

**Improvement.** Zero-touch session continuity. Asking "where were we?" on day 2 invokes `/paper-compiler:resume-session` which reads `list_sessions` + `resume_session` + `get_decisions_since` and returns a one-screen summary.

**Chokepoint.** The auto-scaffold is silent. A user who manually deletes `decisions.md` will find it regenerated empty on next compile with no warning.

---

## 12. Token efficiency

**What changed.**
- `query_chunks` defaults unchanged (snippet-first, `max_per_paper=2`).
- Phase 6 indexes everything, but defaults still favour prose. Tables/captions surface only when their per-kind score floor is beaten.
- The `query` tool (router + community boost) returns fewer chunks on average than v1's `query_chunks` for the same query because the router prunes paper IDs to the top-3 communities before BM25.
- Sub-skill `allowed-tools` whitelists tightened the per-skill context budget.

**Improvement.** Per-five-turn JEPA session: v1 spent ~25K MCP-result tokens; v2 spends ~21K (community routing prunes; sub-skill scoping prevents loading unused references).

**Chokepoint.**
- **`paper_text(full=True)` byte budget still unenforced.**
- **Reranker is unchanged** — BM25 + cosine + quality prior + community boost is still hand-tuned, not learned.

---

## 13. Configuration surface

**What changed.** Additions:

```toml
[sources]                       # NEW (Phase 3)
enabled = ["arxiv", "s2", "openalex", "unpaywall", "crossref"]
contact_email = "you@example.com"
rate_limit_rps = 2.0

[parser]
pdf_backend = "docling"         # default flipped from "marker"

[compile]
# atom_paper_count REMOVED (Phase 5)
```

Env unchanged: `SEMANTIC_SCHOLAR_API_KEY`, `ANTHROPIC_API_KEY`, `PAPER_COMPILER_RESEARCH_DIR`. The last is now resolved from `${CLAUDE_PROJECT_DIR}` by `.mcp.json`, not `${PWD}`.

**Improvement.** Per-source rate limiting and contact email surface in TOML.

**Chokepoint.** Polite-pool identifier needs to be set per-user; `setup.sh` writes a placeholder, not the user's actual email.

---

## 14. Limitations summary

Carry-over from v1 that v2 fixed:
- **Atom-id reshuffle breaking wiki references** — fixed by stable `atom_uid` (§3.6, Phase 1). `atom_id` still reshuffles for filename readability but is no longer a join key.
- **`equation_lookup` stub** — populated by Phase 6 equation-block indexing.
- **Tables excluded from retrieval** — Phase 6 indexes them with a quality floor.
- **Hand-labelled edge accuracy below 75% target** — Phase 4 hit ~78%.
- **MCP-only enforcement via consumer-repo `settings.json`** — moved to PreToolUse hook in the plugin.

Carry-over **still broken**:
- TeX walker fragility on heavy macro use.
- No diagram OCR.
- Reference resolution stays 45–65% on hard corpora (Phase 3 helps acquisition, not resolution).
- Confidently-wrong heuristic classifier still escapes LLM rescue.
- Bimodal LLM atom-extraction quality.
- Louvain resolution 1.4 magic number.
- Wiki articles regenerated wholesale (hand-edits lost).
- `wiki-lint` structural-only, no semantic contradiction detection.
- `graph_sql` prefix-based SELECT check.
- `paragraph_ids` not validated against paper.
- `cache prune` unimplemented; cache grows monotonically (~50–200 MB/paper).

New in v2:
- Memory plane (`decisions.md`, `sessions/`) has no garbage collection.
- `decisions.md` content is not indexed in `chunks_fts` until the next compile.
- 10 bash scripts run in the hook lifecycle; each is exit-code-meaningful, expanding the surface area for breakage.
- Intent-detection hook is regex-only; nuanced prompts route ambiguously.
- DB and embedding-file disk footprint up ~2.5×.
- Phase 5 LLM cost can hit the `--atom-llm-calls` cap on neighborhoods > 80 parsed papers.
- Per-source preference is order-only; can pick HTML-rendered PDFs over arXiv TeX.
- Polite-pool email needs manual config; default placeholder is not a working address.

Fixed in v2.1:
- `find_research_dir()` boundary escape in `stop.sh` + `session-start.sh` — hooks now respect `CLAUDE_PROJECT_DIR` as authoritative and never walk outside it.
- `stop.sh` printf crash (`printf: 0\n0: invalid number`) on sessions with no `record_decision` calls.
- `build-research-context` monitoring blackout — main session now sees real-time build progress via Monitor + background Bash, and MCP tools activate automatically via `bind_research_dir` on completion.

---

## 15. What this hasn't done (v3 candidates)

In order of estimated impact:

1. **Source-quality preference** in `acquire.py` — prefer TeX over publisher PDF when both available.
2. **Decision-rationale re-embedding** — fold `decisions.md` entries into `chunks_fts` between compiles, not just at compile time.
3. **Semantic lint** — LLM pass over `answers/` + `decisions.md` for contradictions.
4. **Delta community detection** — skip recompute on small ingests.
5. **Learned reranker** — fine-tune on labelled query-chunk pairs.
6. **Multi-paper compile** — one shared corpus across N targets (PaperBench).
7. **Diagram OCR** — at minimum, GPT-4o-vision on architecture figures.
8. **Adaptive chunk size** — function of paragraph length and section type.
9. **HTML wiki viewer** — single-page browser for the wiki (Obsidian works today but is not shippable).
10. **Hook auto-fix** — `wiki-lint` moves from warn-only to fix-with-confirmation.
11. **Run the PaperBench eval** in `docs/05` — still pending from v1.
12. **Semantic intent detection** — replace `detect-intent.sh` regex with a tiny classifier.
13. **Cache prune** — implement the v0.2 stub.
14. **Memory-plane GC policy** — rotate or archive `sessions/` and old `decisions.md` entries.

---

## 16. Verification — running the gates locally

v1 gates still pass. v2 adds:

```bash
DB=research/research.db

# Stable atom uids — should be 16 hex, unique
sqlite3 $DB "SELECT atom_uid, COUNT(*) FROM atoms GROUP BY atom_uid HAVING COUNT(*) > 1;"
# expect: empty

# All chunks indexed (Phase 6)
sqlite3 $DB "SELECT is_indexed, COUNT(*) FROM chunks GROUP BY is_indexed;"
# expect: 1 | <total>

# Chunk-kind taxonomy populated
sqlite3 $DB "SELECT chunk_kind, COUNT(*) FROM chunks GROUP BY chunk_kind;"

# Multi-source acquisition (Phase 3) — at least 2 sources unless arXiv covered everything
sqlite3 $DB "SELECT acquired_via, COUNT(*) FROM papers WHERE acquired_via IS NOT NULL GROUP BY acquired_via;"

# Communities embedded (Phase 7)
sqlite3 $DB "SELECT COUNT(*) FROM communities_vec;"
# expect: == COUNT(*) FROM communities

# Memory plane shells exist
ls research/decisions.md research/sessions/ research/CLAUDE-PAPER-CONTEXT.md

# Manifest carries new telemetry
jq '.papers_by_source, .evidence_provenance' research/build-manifest.json
```

Live MCP smoke test additions:

```python
from paper_compiler_mcp.db import open_ro, query_chunks, route_query
from pathlib import Path

conn, vec = open_ro(Path("research/research.db"))

# Router
assert route_query("what is the value of the elite fraction") == "local"
assert route_query("survey of latent world models") == "global"

# Community-boosted query
print(query_chunks(conn, vec, "ablation hyperparameter values", limit=4, kinds=["table"]))
```

---

## 17. The deliberate trades

Carry-over from v1:
- Plane separation (CLI writes, MCP reads structured artifacts).
- Wiki regenerated wholesale.
- Per-paper diversification cap of 2.
- No web-search fallback.
- Heuristic > LLM where it works.

New in v2:
- **Memory plane is human-written markdown, not DB rows.** Trade: less queryable, more `git diff`-friendly. The two MCP write tools are gated `ask` so the user retains veto.
- **Hook-enforced denial.** Trade: the user can't easily disable it without editing the plugin. This is by design — the policy travels with the plugin.
- **Index everything.** Trade: 2.5× disk for the ability to retrieve tables/equations. Accepted.
- **Stable atom_uid + reshuffling atom_id.** Trade: human filenames stay short, machine refs stay durable. Two IDs to remember, but the convention (uid in commits/decisions, id in conversation) is clean.
- **Phase 5 budget allocator over all parsed papers.** Trade: more LLM cost, broader coverage. The `--atom-llm-calls` cap now binds; users who care about cost should lower it.
- **Sub-skill nesting.** Trade: more SKILL files to maintain (24 vs 6), tighter forked context per task. The `allowed-tools` whitelist per sub-skill is the single biggest quality-of-life improvement on retrieval cost.

---

## 18. Glossary

Carry-over from v1 (atom, brief, chunk, community, defining paper, frontier policy, etc.). New in v2:

- **atom_uid** — 16-hex `sha1(normalizer_version, category, canonical_name, defining_paper_id)`. The cross-rebuild stable join key. Use in `decisions.md`, session notes, and code comments. **Never** use `atom_id` for persistence.
- **chunk_kind** — one of `prose | table | caption | reference | equation_block | answer`. Recorded on every row; retrieval can filter or boost on it.
- **community_boost** — multiplicative score adjustment in `query_chunks` for chunks whose `paper_id` belongs to a community returned by `_top_communities(query, k=3)`.
- **CLAUDE-PAPER-CONTEXT.md** — per-paper context fragment emitted on every compile; inlined into the system prompt by the SessionStart hook.
- **decisions.md** — append-only structured gotchas log under `research/`. Written via `record_decision` MCP tool.
- **intent** (edge) — one of `supports | refutes | extends | uses | discusses`. Recorded alongside the eleven role labels by the Phase-4 LLM classifier.
- **memory plane** — `decisions.md` + `sessions/` + `CLAUDE-PAPER-CONTEXT.md`. Additive plane alongside the structured artifact.
- **provenance_rule** — the heuristic rule name (or `"llm"`) that produced an edge's top role. Stored on the `edges` row for audit.
- **route_query / query router** — deterministic regex over query text returning `local | global | hybrid`; drives `query` tool dispatch and community boost.
- **session note** — `research/sessions/<date>-<slug>.md`. One per Claude Code session; populated by `append_session_note` during the session and the Stop hook at end.
- **source preference** — order of `[sources].enabled` in `paper-compiler.toml`. First successful fetch wins; recorded in `papers.acquired_via` and `build-manifest.json::papers_by_source`.
- **stable atom uid** — see `atom_uid`.
- **subcategory** — optional LLM-emitted refinement on an atom (e.g. `category=objective, subcategory=contrastive`). Stored in `atoms.subcategory`; surfaced to community summary + audit sub-skills only.

---

*End of v2 build document. Read alongside `v1_build.md` — the section numbers align, the deltas live here. Update on every v2.x release.*
