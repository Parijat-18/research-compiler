# v1 Build — paper-compiler End-to-End

**Status:** v0.2 (post-Karpathy-wiki + multi-paper atoms + graph traversal)
**Last build verified:** 2026-05-18 on `arxiv:2603.19312` (LeWorldModel/JEPA)
**Companion to:** `docs/01-PRD.md`, `04-architecture.md`, `05-evaluation-plan.md`

This document is the implementation reference. It describes what is built, why it is built, exact mechanics at every stage, and the known limits, bugs, and open issues that follow from the choices made. It is intended to be read top-to-bottom once, then used as a navigable reference.

---

## 1. Hypothesis

The compressed claim:

> Research papers are compressed implementation artifacts. The detail a coding agent needs to reproduce a paper is **distributed across the citation neighborhood**, not contained in the paper alone. A Claude Code plugin that compiles that neighborhood into a queryable Graph RAG store, exposes it through MCP tools, and teaches Claude via skills *which* tool to use for *which* sub-task will produce more faithful reproductions than Claude with web search.

Operational form of the hypothesis (from `docs/05-evaluation-plan.md`):

- **Condition A:** Claude Code + target paper PDF only.
- **Condition B:** Claude Code + `research.md` brief only (no MCP tools).
- **Condition C:** Claude Code + `research.md` + full MCP Graph RAG.

Claim: **C beats A by ≥ +10 percentage points** on PaperBench-style replication scoring, with hallucination rate cut in half, and atom coverage at least 1.5× A.

Secondary claim: **the brief alone (B) carries most of the benefit, but the MCP tools close the last 3–5 pp gap** for non-obvious cross-paper queries.

Tertiary claim: a Karpathy-style llm-wiki **on top of** the Graph RAG turns each compile into a knowledge base that *grows during use* — answers get promoted to articles, citations are stable, and a future Claude Code session inherits the prior session's reasoning instead of re-discovering it.

---

## 2. System overview

Three planes, hard-separated. The contract between them is files in `research/`.

```
┌────────────────────────────────────────────────────────────────────┐
│                  Claude Code session (user-facing)                 │
│   skills:                                                          │
│     /paper-compiler:build-research-context  (manual, forked)       │
│     /paper-compiler:use-research-context    (auto)                 │
│     /paper-compiler:audit-against-research  (auto)                 │
│     /paper-compiler:wiki-query              (auto)                 │
│     /paper-compiler:wiki-ingest             (manual, forked)       │
│     /paper-compiler:wiki-lint               (manual, forked)       │
│   MCP tools: 15 mcp__paper-compiler__* tools                       │
└─────────┬──────────────────────────────────────────▲───────────────┘
          │ queries                                  │ structured evidence
          ▼                                          │
┌────────────────────────────────────────────────────────────────────┐
│            paper-compiler MCP server (`server/`)                   │
│  Lazy-loads research/research.db on first tool call.               │
│  sqlite + sqlite-vec + FTS5; read-only; ~26 MB / paper.            │
└─────────┬──────────────────────────────────────────────────────────┘
          │ reads                                                     
          ▼                                                           
┌────────────────────────────────────────────────────────────────────┐
│              research/  (per-user-repo, on disk)                   │
│   research.md     — human-readable brief ≤ 8000 tokens             │
│   research.db     — sqlite Graph RAG store (FTS5 + sqlite-vec)     │
│   SCHEMA.md       — DB schema reference for Claude                 │
│   missing-details.md                                               │
│   graph.json      — atom graph (also in DB)                        │
│   evidence/<atom>.md  — per-atom verbatim spans                    │
│   wiki/                                                            │
│     index.md / SCHEMA.md / log.md                                  │
│     atoms/<atom-id>.md                                             │
│     papers/paper-<safe-id>.md                                      │
│     communities/community-<n>.md                                   │
│     answers/<slug>.md  — Claude-written, promoted Q&A              │
└─────────▲──────────────────────────────────────────────────────────┘
          │ writes                                                    
          │                                                           
┌────────────────────────────────────────────────────────────────────┐
│       paper-compiler CLI (`cli/`)  — runs in forked subagent       │
│   stages: resolve → acquire → parse → expand → classify →          │
│           atom-extract → score → render → build DB → wiki          │
│   external: Semantic Scholar API + arXiv mirror + Anthropic LLM    │
└────────────────────────────────────────────────────────────────────┘
```

**Why the strict separation:** the MCP server **never** writes; the CLI **never** serves runtime queries. This means a stale DB can be diagnosed without rerunning a compile, and a buggy MCP tool can be replaced without re-acquiring papers.

**Limitation of the model.** The hard plane separation costs us one feature: the MCP server can't ask the CLI "please re-acquire this paper". If a paper is missing, the user must run `/paper-compiler:wiki-ingest <id>`. This was a deliberate trade — see §17.

---

## 3. The CLI compile pipeline

Nine stages. Each writes to disk. Each is independently resumable via the content-addressed cache. Entry point: `paper-compiler build <id-or-url> --out research/ [flags]`.

### 3.1 Stage 1 — Resolve

**File:** `cli/src/paper_compiler_cli/resolve.py`

**Input:** arXiv id, DOI, S2 id, URL, or local PDF/TeX path.

**Algorithm:**
1. `_normalize()` strips URL wrappers (`arxiv.org/abs/…`, `doi.org/…`, `semanticscholar.org/paper/…`) and returns one of `ARXIV:<id>`, `DOI:<doi>`, a 40-hex S2 id, or a raw search query.
2. If the input is a local file path, extract a title heuristic from the filename and fall back to S2 search.
3. Call `S2Client.get_paper(token)` for canonical resolution; if it fails, search by full input string.

**Output:** one or more `Candidate(paper_id, title, year, authors, external_ids, confidence)` records.

**Known issues:**
- DOI parsing is regex-based; rare DOIs with unusual characters can be misclassified. Workaround: pass the arXiv id when available.
- `resolution_confidence` defaults to `0.6` for search-based matches, which is generous. The build skill is supposed to ask the user to confirm when `confidence < 0.9`, but this gating is not enforced when called non-interactively.

### 3.2 Stage 2 — Acquire

**File:** `cli/src/paper_compiler_cli/acquire.py`

**Acquisition order (first hit wins):**

1. **arXiv e-print tarball.** `https://arxiv.org/e-print/<arxiv-id>` — almost always TeX source. Extracted to `~/.cache/paper-compiler/papers/<paper-id>/tex/`.
2. **S2 `openAccessPdf.url`.** Fetched as `openaccess.pdf`.
3. **User-provided local file** (only if explicitly passed).

If none succeed, the paper is recorded as `unacquirable` and skipped from atom extraction (metadata still goes into the DB).

**Known issues:**
- arXiv tarballs sometimes contain a single PDF instead of TeX source; the code falls back but loses citation parsing fidelity.
- HTTP failures on the e-print mirror are seen in ~3% of papers in dense compiles. We log and continue; the paper becomes metadata-only.
- `openAccessPdf.url` is sometimes a redirect to an HTML landing page; the resulting "PDF" is bytes of HTML. Not currently detected.
- Downloads aren't authenticated; rate-limited sites (Springer, Elsevier) return 403. Acceptable — these are also closed-access.

### 3.3 Stage 3 — Parse to IR

**Files:** `cli/src/paper_compiler_cli/parse/__init__.py`, `parse/tex.py`, `parse/pdf.py`, `ir.py`.

**IR schema** (`ir.py`, pydantic):

```python
class Paper(BaseModel):
    schema_version: str = "1.0"
    paper_id: str               # "s2:<40-hex>"
    external_ids: ExternalIds   # arxiv, doi, corpus_id
    metadata: Metadata          # title, authors, year, venue, abstract
    acquisition: Acquisition    # source, fetched_at, cache_path
    sections: list[Section]     # tree of Sections → Paragraphs
    equations: list[Equation]   # latex + section_id + mentioned_in
    algorithms: list[Algorithm]
    tables: list[Table]
    figures: list[Figure]
    references: list[Reference] # ref_id + raw + resolved_paper_id
```

**TeX path** (`parse/tex.py`) — preferred:
1. `_find_main_tex()` — pick the `.tex` file containing `\documentclass` and `\begin{document}`; fall back to the largest `.tex`.
2. `_expand_inputs()` — **recursively** inline `\input{...}` and `\include{...}` up to depth 6, with cycle detection. This was a v0.1 bug that left out-of-tree sections invisible; fixed in v0.2.
3. Strip LaTeX comments.
4. Walk the expanded source with `pylatexenc.LatexWalker`. Section macros (`\section`, `\subsection`, `\subsubsection`, `\paragraph`) open a new `Section`; their textual depth maps to `level`.
5. Equation environments (`equation`, `align`, `gather`, `multline`, `eqnarray`, and `*` variants) become `Equation` records with the verbatim LaTeX.
6. `algorithm` / `algorithmic` environments become `Algorithm` records.
7. Citations: every `\cite{key}` (and `citep`, `citet`, `autocite`, `parencite`, `textcite`, `citealp`, …) is captured. Cite keys are resolved against:
   - `.bib` files discovered under the source dir, parsed by `bibtexparser`.
   - `\bibitem{key}` blocks inside `\begin{thebibliography}` (handled by `_load_thebibliography`).
   The merged map populates `Reference.raw` for each cite key.
8. Section type is classified by `classify_section_title()` — a small ruleset over title keywords (`method`/`approach` → `method`, `experiment`/`setup` → `experiments`, etc.). Fallback: `other`.

**PDF path** (`parse/pdf.py`) — fallback when no TeX:
1. Run `marker-pdf` (`PdfConverter` + `text_from_rendered`) → markdown.
2. Split markdown by `#`-headings into sections.
3. Capture `[N]` and `[N, M]` style numeric citations as `Reference` records and `Citation` links.
4. `$$…$$` blocks become `Equation` records.

**Known issues:**
- TeX walker is finicky on heavy macro-rebinding (NeurIPS templates with custom `\@theorem` defs). We catch `LatexWalker` exceptions and continue with whatever was parsed up to that point — sometimes resulting in a paper with only 2–3 sections.
- `_load_thebibliography` only matches `\bibitem{...}` literally; if a paper defines a macro for it, references aren't recovered.
- PDF path is **not currently active in default installs** because `marker-pdf` is an optional extra (`pip install paper-compiler-cli[pdf]`). Marker pulls torch + a ~3 GB checkpoint. Acceptable for users who hit a non-arXiv paper; not for the default install.
- The parser does not preserve table contents — only captions. This is a deliberate choice (table content tends to pollute retrieval; see §3.7).
- Figures are caption-only; no OCR. Diagrams that describe architecture details are invisible to the compiled context.

### 3.4 Stage 4 — Expand neighborhood

**File:** `cli/src/paper_compiler_cli/expand.py`

This is the citation-graph expansion. It produces the set of papers to consider as the neighborhood, **plus** acquires + parses the top-priority ones so their full text lands in the chunks/atoms pipeline.

**Two passes:**

**Pass A — reference resolution.** Every `Reference` from the target paper gets a `resolved_paper_id`:
1. `_parse_bib_raw()` extracts `title`, `author`, `year`, `url`, `journal`, `booktitle` from the BibTeX-flattened raw string.
2. Look for an arXiv id (`\d{4}\.\d{4,5}`) or DOI inside either `raw` or `url`. If found, call S2 `/paper/ARXIV:<id>` or `/paper/DOI:<doi>` directly — these resolve at ~0.97 confidence.
3. For the residual (no arXiv/DOI), perform a title-based S2 search. **Score each candidate** by:
   - Author overlap (last names normalized to lowercase).
   - Year exact match (+0.4).
   - Token overlap with the queried title.
   Accept the best candidate only if total score ≥ 0.4. Confidence = `min(0.9, 0.4 + best_score / 2)`.

If the local parser yielded fewer than `max(5, 30% of references)` resolved, also call S2's `/paper/<id>/references` endpoint (`_seed_from_s2_references()`) and merge results back into `target.references`, matched by token overlap against the bibliography raw strings.

**Pass B — frontier expansion.** Per `docs/04-architecture.md §3.4`:
1. Build "raw edges" — paragraph-anchored citation occurrences with section_type, surrounding context, and nearby equation/algorithm/table refs.
2. **Synthesize phantom edges** for resolved references that produced no paragraph citation (common when bib has more entries than body cites). These appear with `section_id=""`, `section_type="other"`, so they don't pollute the high-priority signal but are still in the neighborhood.
3. Compute per-paper **priority** (`_priority()`):
   - section_type weights (`method=1.0`, `experiments=0.8`, `results=0.6`, `related_work=0.15`, …).
   - +0.4 for proximity to equation.
   - +0.3 for proximity to algorithm.
   - +0.2 for proximity to table.
   - +0.2 if S2 marks the cited paper "influential" (`influentialCitationCount > 5`).
   - +0.1 per additional occurrence (repeated citation boost).
4. Sort. Cap to `max_papers` (default 200, configurable). Keep depth-1 papers.
5. **Depth-2** (if `max_depth >= 2`): for the top-K depth-1 papers (`expand_top_k`, default 20), fetch S2 references and add each to the neighborhood with `priority = 0.5 * parent.priority`.
6. **Acquire + parse** the top-priority papers (those with `priority >= 0.5` at depth ≤ 2). This is the key v0.2 change — neighborhood papers now have full parsed text in the DB. Bounded concurrency (4) and respects the wall-time + S2 budget.

**Hard caps** (configurable via CLI flags):
- `--max-depth N` (default 2; max 3).
- `--max-papers N` (default 200).
- `--max-s2-requests N` (default 500). Hard stop on the S2 API.
- `--max-wall-seconds N` (default 1200).
- `--top-k N` (default 20).
- `--atom-papers N` (default 10) — how many cited papers get atom extraction. New in v0.2.

**Known issues:**
- Title-search resolution returns the first-best result even on ambiguous searches (two papers with the same title). Author scoring mitigates this; doesn't eliminate.
- S2 batch endpoint (`/paper/batch`) is currently used only for metadata enrichment, not for the initial reference resolution loop. There's headroom to cut 30–50% of S2 calls by batching.
- Depth-2 priority inheritance (`0.5 * parent`) is heuristic and untuned. Papers reached only through one depth-2 path with low parent priority often have inflated priority compared to direct depth-1 papers.
- Coverage (`references_resolved / references_attempted`) typically lands at **45–65%**. Remaining unresolved references tend to be workshop papers, technical reports, software releases. Most are not implementation-critical, but some are.

### 3.5 Stage 5 — Classify citation edges

**Files:** `cli/src/paper_compiler_cli/classify/__init__.py`, `heuristic.py`, `llm.py`, `edge.py`.

For every raw edge, classify it into one of the eleven PRD §12 implementation roles:
```
architecture_dependency, loss_function_dependency, dataset_dependency,
preprocessing_dependency, evaluation_protocol_dependency, baseline_dependency,
optimizer_or_training_trick, theoretical_assumption, ablation_reference,
engineering_reference, related_work_only
```

**Hybrid classifier:**

1. **Heuristic pass** (`heuristic.py`):
   - **Section prior:** `method` boosts architecture/loss/preprocessing; `experiments` boosts dataset/evaluation/baseline; `related_work` flips on `related_work_only`.
   - **Text hints:** small hand-curated keyword sets (e.g. LOSS_HINTS = `loss objective log-likelihood kl cross-entropy contrastive reward penalty`). Each hit contributes weight to the matching role.
   - **Artifact proximity:** equations → +0.25 to loss / +0.15 to architecture / +0.15 to theory; algorithm boxes → +0.2 architecture / +0.2 optimizer; tables → +0.2 to baseline / evaluation.
   - **Title prior** on cited paper (e.g. "dataset" in title → +0.3 dataset; S2 `publicationTypes=["Dataset"]` → +0.4).
   - Scores are normalized; top role is returned with confidence = `min(0.95, score / total)`. Up to 3 ranked roles per edge.
2. **LLM residual** (`llm.py`):
   - For edges where heuristic top-confidence < `LLM_THRESHOLD = 0.55` and budget remains (`--classifier-llm-calls`, default 50).
   - Calls the unified `llm.call_llm()` backend (see §6) with the citation context + nearby artifact ids + cited title.
   - Returns the structured JSON; merges into the role list.

**Output:** `ClassifiedEdge(edge, [(role, confidence)], classifier="heuristic"|"llm")` for every edge.

**Known issues:**
- Heuristic accuracy is OK on method-section edges, mediocre on experiments-section edges where wording is often subtle (a baseline is "compared to" but also "concurrent with"). Hand-labeled accuracy on a 100-edge dev sample was ~72% per role, below the 75% target in `docs/05`.
- LLM residual fires only on edges where heuristic confidence is low. If the heuristic is confidently wrong (high score, wrong label), LLM never sees it.
- No multi-label support beyond top-3; a paper that is both a dataset and a baseline gets only one role recorded as `best_role`. The `edge_roles` table stores all ranked roles for multi-label use, but most downstream tools read `best_role`.

### 3.6 Stage 6 — Atom extraction

**File:** `cli/src/paper_compiler_cli/atoms/extract.py`

Atoms are the unit Claude actually queries. Categories: `architecture, loss, dataset, preprocessing, evaluation, baseline, optimizer, hyperparameter, training_trick`.

**v0.2 change: multi-paper extraction.**

The helper `_extract_for_paper(paper, …)` walks the method sections of one paper, runs both heuristic name-spotting (`_scan_paragraph()` — regexes for known architectures/losses/datasets/optimizers) and an LLM call per method paragraph (budget-bounded), and emits `Atom` records.

`extract_atoms()` calls `_extract_for_paper` for:
1. The **target paper** with `priority_factor = 1.0`.
2. The **top-`atom_paper_count` acquired cited papers** (default 10) sorted by `priority`, with `priority_factor = 0.6` so target atoms still dominate.

Each extracted atom gets:
- `id` (sequential `atom-NNN`).
- `name`, `category`, `description` (first 240 chars of the scrubbed paragraph or the LLM's description).
- `defined_by_paper_id` — assigned via `_find_defining_paper()`: if the same paragraph cites another paper whose classified role matches the atom's category, that paper is the defining paper; otherwise the atom's home paper.
- `used_by_paper_ids` — accumulated when the same atom key (`{category}:{normalized_name}`) appears in multiple papers.
- `evidence_span_ids` — one `EvidenceSpan` (`ev-NNN`) per atom; verbatim text of the source paragraph.
- `priority` — set by `priority_factor`.

**Junk filters** (lessons learned from v0.1 — see §17):
- `_is_junk_name()` rejects names >80 chars, >10 words, length<3, all-stopwords, or `<4 letters`.
- `_scrub()` strips `<graphics>`, `<cit.>`, `\includegraphics{…}`, `\ref{…}`, `\eqref{…}`, `\label{…}` placeholders left by Marker / pylatexenc.
- Stricter regexes than v0.1: `NAMED_DATASET_KNOWN_RE` is a whitelist of real dataset names; `NAMED_DATASET_PHRASE_RE` matches only "<Name> dataset|benchmark|corpus|environment|simulator" phrases. Loose match on CamelCase words was the v0.1 bug that pulled out "This", "Architecture", "Predictive" as datasets.

**Experiments-section atoms.** After method extraction, walk experiments/results sections and create dataset/evaluation/baseline atoms for each paragraph that has a classified edge with one of those roles, using the cited paper's title as the atom name. Evidence span = the experiment paragraph.

**Dedup** (`atoms/dedup.py`):
1. **Exact normalize:** same `(category, tokens(name) − stopwords)` → merge.
2. **Jaccard / containment:** for atoms in the same category, Jaccard ≥ 0.6 or containment ≥ 0.85 → merge.
3. **Embedding cosine** (optional, runs if `sentence_transformers` is installed): for atoms in the same category, cosine ≥ 0.92 on `BAAI/bge-small-en-v1.5` (384-dim) embeddings → merge.

Merging keeps the higher-priority atom and folds `used_by_paper_ids`, `evidence_span_ids`, `dependencies`.

**Known issues:**
- LLM extraction quality is bimodal: when the prompt sees a clean method paragraph it nails the atoms; when the paragraph is short or mostly notation it returns 0–1 atoms, padding cost without information.
- Heuristic name-spotting still mislabels some atoms (a paper's "Optimization Steps" hyperparameter gets `category=hyperparameter` but its description becomes the surrounding CEM paragraph — the description is fine, the name is technically correct, but a less ambitious atom would be cleaner).
- Multi-paper extraction skew: when a JEPA paper cites 10 robotics papers, robotics atoms dominate the count (see actual JEPA result: top defining papers are DINO-WM, AdaptiGraph, RT-2). This is not a bug per se — those atoms are real and useful — but it shifts the distribution away from the target's own contributions. Tunable via `--atom-papers N` (set to 0–3 if you want target-only focus).
- Dedup's embedding pass requires the same model dimension as the DB's `atoms_vec` table (384). Loading SPECTER2 (768) silently no-ops; we fixed the load order so `bge-small` is tried first.
- Atom ID assignment is global-sequential, not stable across compiles. Re-running a compile reshuffles `atom-NNN` ids. This will break wiki-cross-links on re-compile unless we add a deterministic id derived from `(category, normalized_name)` in v0.3.

### 3.7 Stage 7 — Score and rank

**File:** `cli/src/paper_compiler_cli/score.py`

Two per-paper scores:

```
scholarly_influence = 0.3*log(cc+1) + 0.4*log(icc+1) + 0.3*recency
implementation_influence = sum(edge_confidence) + 0.3*per_method_edge + 0.5*atoms_defined_count
                           + 0.2 if equation-adjacent edge + 0.3 if algorithm-adjacent
rank = 0.7*implementation_influence + 0.3*scholarly_influence
```

`scholarly_influence` uses S2's `citationCount`, `influentialCitationCount`, and a linear recency window (year, decaying from 2026 over 30 years).

**Topological order** for `implementation_order`: atoms sorted by category priority (`dataset → preprocessing → architecture → loss → optimizer → …`) then DFS over `dependencies` to settle inter-atom dependencies.

**Known issues:**
- Weights are guesses, not tuned. The 0.7/0.3 split is a v0.1 placeholder.
- `dependencies` between atoms is rarely populated by the extractor; topological order mostly reduces to category order.
- `scholarly_influence` for a 2024 paper that 1000 citers haven't caught up to is artificially low. We compensate with implementation_influence dominance, but a paper that's important *and* recent gets under-ranked.

### 3.8 Stage 8 — Build the Graph RAG DB

**Files:** `cli/src/paper_compiler_cli/graph_db.py`, `server/src/paper_compiler_mcp/db.py`.

This is the central runtime artifact. One sqlite file at `research/research.db`, with sqlite-vec + FTS5.

**Schema** (key tables; full in `research/SCHEMA.md`):

```
papers(paper_id PK, title, year, venue, authors_json, abstract,
       rank, scholarly_influence, implementation_influence,
       is_target, depth, acquired, parsed_path)

sections(section_id PK, paper_id FK, title, section_type, ord)

chunks(chunk_id PK AUTOINCREMENT, paper_id FK, section_id FK,
       paragraph_id, ord, text, n_tokens,
       is_indexed INTEGER, quality REAL)              ← v0.2 columns

chunks_fts  -- FTS5 virtual table over chunks.text + paper_title + atoms_mentioned
            -- populated only when is_indexed = 1
chunks_vec  -- vec0 virtual table, float[384] embeddings keyed by chunk_id
            -- populated only for indexed chunks

atoms(atom_id PK, name, category, defined_by_paper_id FK, description, priority)
atoms_fts  -- FTS5 over atoms.name + description + category
atoms_vec  -- vec0 virtual table for atom-level semantic search

atom_paper_usage(atom_id FK, paper_id FK, role)       -- many-to-many "uses"
atom_evidence(evidence_id PK, atom_id FK, chunk_id FK, verbatim_text)

edges(edge_id PK, from_paper_id, to_paper_id, best_role, best_confidence,
      section_type, paragraph_id, classifier, context)
edge_roles(edge_id FK, label, confidence)             -- multi-label

equations(equation_id PK, paper_id, section_id, latex)
communities(community_id PK, label, summary, size)
community_papers(community_id FK, paper_id FK)
community_atoms(community_id FK, atom_id FK)
missing_details(md_id PK, question, category, options_json, …)
meta(key, value)                                       -- target_paper_id, compiled_at, schema_version
```

**Why sqlite + sqlite-vec.** Single file, no daemon, MCP server opens read-only, ships in the user's repo alongside `research.md`. The Karpathy llm-wiki ethos: artifacts you can `git diff`.

**Indexing rule:** only chunks with `is_indexed = 1` are inserted into `chunks_fts` and `chunks_vec`. The decision is made by `text_utils.is_indexable(section_type, section_title, text)`. See §3.9 below.

**Embeddings model:** `BAAI/bge-small-en-v1.5` (384-dim). Selected because:
- Lightweight (~120 MB), fast CPU encode.
- 384-dim matches the schema (see "match the chunks_vec dim" comment in `compile.py`).
- Generic but solid on scientific text.
- SPECTER2 (768-dim) would be more scholarly-aware but requires schema migration.

### 3.9 Chunking and quality filtering

**File:** `cli/src/paper_compiler_cli/text_utils.py`

Chunks are the retrieval unit. Quality of chunks dominates retrieval quality, which dominates downstream answer quality. v0.1 had a naive chunker; v0.2 added explicit filtering.

**Chunk generation** (`graph_db.py::_chunk_paragraphs`):
1. For each paragraph in the parsed IR, scrub LaTeX placeholders with `scrub_placeholders()`.
2. If the cleaned text is ≤ `target_chars` (default 750), it's one chunk.
3. Otherwise, `split_with_overlap()` splits on sentence boundaries with 200-char overlap between adjacent chunks. Adjacent chunks share the tail/head so context windows that straddle a chunk boundary still read coherently.
4. Each chunk inherits the source paragraph_id (so multiple chunks from the same paragraph share an anchor).

**Quality scoring** (`text_utils.py::prose_quality`) — 0..1 score combining:
- **Hard rejects** (return 0.0): letter ratio < 0.5, digit ratio > 0.25, table-punct ratio > 0.04, < 20 words, avg word length > 12 or < 3.
- **Soft score:** weighted sum of letter ratio (50%), word count saturating at 100 (30%), inverse digit ratio (20%).

**Indexing decision** (`is_indexable`):
- If `quality == 0`, do not index.
- If `section_type` is `appendix` or `other`, only index if the section title contains a method-adjacent keyword (`method`, `approach`, `architecture`, `algorithm`, `training`, `loss`, …). Method-adjacent appendix sections (proofs, supplementary derivations) often contain real content.
- Otherwise, index.

**Effect on JEPA build:** 14,228 total chunks → **5,672 indexed** (40%). The other 60% (mostly tables, figure captions, references list paragraphs, layout dumps) stay in `chunks` (addressable via `chunk_id` if needed) but never appear in FTS or vec search results.

**Embedding generation** (`compile.py`): after the DB is built, embed only the indexed chunks with `bge-small`. ~5,700 chunks × 384 dim × float32 = ~9 MB on disk for JEPA. Atom embeddings written separately (~25 KB).

**Known issues:**
- Quality scoring uses fixed thresholds, not learned. Tuning would help on math-heavy papers where letter-ratio dips.
- A chunk that crosses a sentence boundary mid-equation can have a legit prose-like ratio but be useless. We don't detect this.
- Tables are entirely rejected by the digit-ratio rule. Some tables (e.g. an ablation table comparing hyperparameter choices) carry implementation signal. They're addressable by `paper_text(..., chunk_ids=[N])` if the user knows the id, but never retrieved by search.
- The 200-char overlap is fixed. Long paragraphs (e.g. dense related-work sections) produce many overlapping chunks; short paragraphs no overlap. Adaptive sizing would help.

### 3.10 Stage 9 — Communities

**File:** `cli/src/paper_compiler_cli/communities.py`

**Graph construction** (`_build_graph`):
- Nodes: papers.
- **Strong edges:** classified citation edges (weight = edge confidence).
- **Medium edges:** if atom A is defined by paper P and used by paper Q, add edge (P, Q) weight 0.3.
- **Weak edges:** for each pair of papers sharing ≥ 2 atoms in the same category, add edge weight 0.2.

This was the v0.2 fix. v0.1 only used citation edges → on a sparse 42-edge / 257-paper graph the modularity detector collapsed everything to one community.

**Detection** (`_detect`):
- Primary: `networkx.community.louvain_communities(g, weight="weight", resolution=1.4, seed=42)`. Resolution > 1 promotes more, smaller communities.
- Fallback (if NetworkX version doesn't have Louvain): `greedy_modularity_communities`.

**Summarization:** for each community with size ≥ 2, build a JSON payload of papers (title + year + abstract) and atoms (name + category + description), and call `llm.call_llm()` for a 2–4 sentence summary + a 2–5 word community label. Capped at `max_llm_calls` (default 12).

**Storage:** `communities`, `community_papers`, `community_atoms` tables.

**JEPA result:** **3 communities** — "JEPA World Models" (22 papers), "Visual World Models Planning" (4), "Graph-Based Adaptive Robot Dynamics" (3). Real, distinct, labelled by the LLM correctly.

**Known issues:**
- Louvain is stochastic in general; we seed it but resolution = 1.4 is a magic number that worked on JEPA. Other corpora may want 1.0 (fewer, larger communities) or 2.0 (many small clusters).
- Communities are rebuilt **wholesale** on every compile; an `ingest` operation also rebuilds them. This is fine for ≤ 500 papers; would need delta updates beyond that.
- LLM budget for summarization is independent of `--classifier-llm-calls` and `--atom-llm-calls`. Easy to overlook.

### 3.11 Render: research.md + wiki + DB

`compile.py::build_paper` orchestrates the full pipeline, then writes:

1. `research/research.md` — human-readable brief, ≤ 8000 tokens (enforced via `tiktoken`).
2. `research/missing-details.md` — open implementation questions found by `collect_missing_details()`.
3. `research/graph.json` — atom graph as JSON (also in DB).
4. `research/evidence/<atom-id>.md` — per-atom verbatim evidence packs.
5. `research/research.db` — the Graph RAG store.
6. `research/SCHEMA.md` — DB schema reference (regenerated each compile).
7. `research/embeddings.npy` + `embeddings.json` — chunk-level embeddings (alongside the DB-stored vec0 table; kept as files for `--no-vec` use cases).
8. `research/wiki/` — the Karpathy llm-wiki (§4).
9. `research/build-manifest.json` — counts, wall time, coverage, llm backend used.

---

## 4. The wiki — Karpathy llm-wiki implementation

**Problem:** the compiled brief + DB is great for one session. But knowledge accumulated *during* a session (Claude reading chunks, synthesizing across papers, answering a specific question) is lost when the session ends. Web-search-style RAG loses everything between calls.

**Solution (from Karpathy's [gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)):** treat the wiki as a *living* knowledge base that grows during use:
- **Ingest:** read sources → write articles → update index.
- **Query:** answer → promote good answers to articles.
- **Lint:** periodic health-check for contradictions / orphans / stale claims.

**Implementation files:**
- `cli/src/paper_compiler_cli/render/wiki.py` — static wiki generation at compile time.
- `cli/src/paper_compiler_cli/render/wiki_log.py` — append-only event log.
- `cli/src/paper_compiler_cli/render/wiki_schema_doc.py` — emits the wiki SCHEMA.
- `cli/src/paper_compiler_cli/ingest.py` — `paper-compiler ingest` CLI subcommand.
- `plugin-scaffold/skills/wiki-query/`, `wiki-ingest/`, `wiki-lint/` — three new skills.

### 4.1 Article tree

```
research/wiki/
├── index.md                catalog, regenerated on every compile
├── SCHEMA.md               article schema contract (Claude reads this once)
├── log.md                  append-only event log
├── atoms/atom-NNN.md       one article per implementation atom
├── papers/paper-<safe-id>.md   one per acquired paper
├── communities/community-N.md  one per detected community
└── answers/<slug>.md       promoted Q&A answers (written during a session)
```

**Atom articles** (`render_atom_article`):
- Category, atom_id, defining paper link, priority.
- Description.
- Per-evidence-span verbatim quote with paper + section + section_type metadata.
- "Related atoms" — up to 6 same-category siblings.
- MCP query examples specific to this atom (`get_evidence(atom_id="atom-NNN")`).

**Paper articles** (`render_paper_article`):
- Title, authors, year, paper_id, ranks.
- Abstract.
- "Atoms defined here" + "Atoms used by this paper".
- "Cited by" + "Cites" — incoming/outgoing citation edges with role + confidence.
- Query examples.

**Community articles** (`render_community_article`):
- LLM-generated label + summary.
- Member papers + member atoms.

**Bug fixed in v0.2:** v0.1 wrote `atoms/atom-atom-001.md` because the helper used `f"atom-{a.id}"` while `a.id` was already `"atom-001"`. Now `atoms/atom-001.md`.

### 4.2 Append-only log

`research/wiki/log.md` records events. Format:

```
## 2026-05-17T21:33Z — compile
- target: `s2:530dab86…`
- papers in neighborhood: 256 (134 acquired)
- atoms: 153
- communities: 3
- wall: 1052.2s
- llm backend: claude_cli
```

Event types: `compile`, `ingest`, `query` (only promoted answers), `lint`. Writers:
- `compile.py` calls `wiki_log.log_compile()`.
- `ingest.py` calls `wiki_log.append_log("ingest", …)`.
- `wiki-query` skill (Claude-driven) writes a `query` entry.
- `wiki-lint` skill writes a `lint` entry.

**Why append-only:** lets you `git log` the wiki history and answer "when was this last touched?". No rotation in v1; lint will suggest archiving when log > 500 lines.

### 4.3 Wiki SCHEMA.md

`wiki/SCHEMA.md` (generated by `wiki_schema_doc.py`) is the contract for article shapes. Claude reads it once to learn:
- Filename conventions (`atom-NNN.md`, `paper-<safe>.md`, `community-N.md`, `<slug>.md`).
- Required frontmatter on `answers/<slug>.md` (`question`, `asked_at`, `answered_with: {atoms, papers, chunks}`).
- Wikilink conventions (`[[id]]` or `[[id|display]]` — id matches basename without `.md`).
- Log entry format.

This is **not** the DB schema (that's `research/SCHEMA.md`). Two separate schemas: one for the wiki article tree, one for the SQLite DB.

### 4.4 Wiki workflow skills

**`/paper-compiler:wiki-query <question>`** — auto-invocable. The canonical entry point for "answer a question about this corpus":

1. Read `wiki/index.md`.
2. Find relevant atoms via `find_atom`; possibly walk the graph via `neighborhood_subgraph` or `shortest_path`.
3. Pull evidence via `query_chunks` (snippet-first) and `paper_text` (with `paragraph_ids`).
4. Synthesize a 2–8 paragraph answer with inline citations:
   - `[[atom-013|CEM optimizer]]` for atoms.
   - `[[paper-s2_5c5e6938…|Rubinstein 1999]]` for papers.
   - `(chunk_id=46)` for raw chunks.
5. **Promote** if: ≥ 2 atoms cited across ≥ 2 communities, or ≥ 3 distinct chunks. Save as `wiki/answers/<slug>.md` with required frontmatter (per `wiki/SCHEMA.md`).
6. Append a `## … — query` entry to `wiki/log.md`.

`skills/wiki-query/references/promotion-rules.md` documents when to promote; `references/log-format.md` documents the log entry shape.

**`/paper-compiler:wiki-ingest <paper-id-or-url>`** — manual, forked subagent. Adds *one* more paper to an existing compiled corpus:

1. Verify `research.db` exists.
2. Shell out to `paper-compiler ingest <id> --research-dir research/`. The CLI subcommand:
   - Resolves the paper.
   - Refuses if already in DB (unless `--force`).
   - Acquires + parses it.
   - Extracts atoms (priority 0.6).
   - Inserts everything into `research.db`.
   - Recomputes communities from the full DB graph.
   - Re-renders the wiki articles (cheap — markdown only).
   - Appends a `## … — ingest` entry to `wiki/log.md`.
3. Read `wiki/log.md` and report the new entry verbatim.

**`/paper-compiler:wiki-lint`** — manual, forked subagent. Health-check pass:
- Inventory files → set of valid ids.
- Find broken `[[wikilinks]]`.
- Find orphan atoms (no inbound links).
- Find atoms whose defining paper is no longer in DB.
- Find resolved missing-details (answers covering still-open questions).
- Suggest log rotation if > 500 lines.
- Write `wiki/lint-report.md` with `## Broken wikilinks`, `## Orphans`, etc.
- Append `## … — lint` to `wiki/log.md`.

**Warn-only in v1** — no auto-fix. Fix is v2.

### 4.5 Answers — the promotion mechanism

`wiki/answers/<slug>.md` is the only directory Claude writes into during a session. Frontmatter is mandatory:

```yaml
---
question: "<the original user question>"
asked_at: "2026-05-17T21:50Z"
answered_with:
  atoms: ["atom-013", "atom-006"]
  papers: ["s2:530dab…"]
  chunks: [46, 1287]
---
```

This means answers are *machine-readable* — a future ingest pass could re-embed them into `chunks_fts` so they're searchable alongside paper text. v1 doesn't do that pass automatically; the next compile re-runs everything and the answer becomes a regular wiki article (`is_indexed=1` since it's prose).

### 4.6 What problem does the wiki solve?

Three concrete problems:

1. **Session-to-session memory.** Without the wiki, every Claude Code session starts cold. With it, the previous session's synthesized answers are addressable artifacts that future sessions can `Read()` or `wiki-query` over.
2. **Citation stability.** A wiki article with frontmatter `answered_with: {atoms: [atom-013], chunks: [46]}` is a stable contract. The next compile may shuffle `atom-013`'s id (see §3.6 known issues), but the answer file remembers what it cited.
3. **Knowledge accumulation across papers.** If you compile paper A on Monday and paper B (which builds on A) on Wednesday, `wiki-ingest` updates communities and refreshes related articles. The answer "what does paper B inherit from paper A?" lives in `answers/` and survives both compiles.

**Limitations:**
- Wiki articles are regenerated wholesale on every compile. **Hand-edits are lost.** This is intentional but surprising; the doc says "never edit a generated article in place".
- `answers/` is the only directory not wiped on recompile. Atom-id reshuffle still poses risk: an answer citing `atom-013` may end up referring to a different atom after the next compile. We need stable ids (v0.3).
- `wiki-lint` is structural only; it doesn't catch *semantic* contradictions (paper X claims A; paper Y claims ¬A). That's a v2 LLM-driven lint.
- Index.md regenerates from scratch each compile and lists all atoms/papers; on a 250-paper corpus the index is ~10 KB. Browsable but not search-optimized.

---

## 5. The MCP server — what Claude actually calls

**File:** `server/src/paper_compiler_mcp/server.py`. Uses `FastMCP`. Lazy-loads the DB on first tool call (cold start < 2s per `docs/03 §11`).

Fifteen tools. Grouped by purpose:

**Paper-level navigation:**
- `paper_summary(paper_id)` — metadata + atoms defined/used by this paper.
- `citation_neighbors(paper_id, role=None)` — 1-hop citation edges, optionally filtered by role.

**Atom-level:**
- `find_atom(query, limit=5)` — hybrid BM25+vec atom search.
- `get_evidence(atom_id)` — all evidence spans for an atom.
- `compare_methods(atom_a, atom_b)` — side-by-side evidence comparison.
- `trace_dependency(component)` — full chain for one of `architecture, loss, dataset, preprocessing, evaluation, baseline, optimizer`.
- `equation_lookup(symbol_or_keyword)` — currently a stub that returns empty list unless `research/equations.json` is populated. **TODO: wire to the equations table.**

**Chunk-level (Graph RAG core):**
- `query_chunks(query, limit=8, full=False, max_per_paper=2)` — hybrid FTS5 + vec0. Snippet-first by default; pass `full=True` to receive verbatim text. Diversified to ≤ `max_per_paper` chunks per paper. Only indexed chunks participate.
- `paper_text(paper_id, section_type=None, paragraph_ids=None, chunk_ids=None, full=False)` — return chunks of one paper. Snippet-first. Use `paragraph_ids`/`chunk_ids` to pull exact chunks after a query.

**Graph traversal (new in v0.2):**
- `neighborhood_subgraph(node_id, hops=2, role_filter=None, limit=40)` — BFS around a paper or atom. Returns:
  ```
  {
    "root": {"id", "kind": "paper"|"atom", "label"},
    "nodes": [{"id", "kind", "label", "category"?}],
    "edges": [{"src", "dst", "kind": "citation"|"has_atom"|"defines"|"uses_atom", "role"?, "confidence"?}],
    "via_atoms": [{"atom_id", "label", "papers": [...]}],
    "truncated": bool
  }
  ```
- `shortest_path(from_id, to_id, max_hops=4, k=3, role_filter=None)` — up to k shortest paths over a NetworkX graph built lazily from the DB. Edge weight = `1 / confidence` so high-confidence citations are preferred.

**Community-level:**
- `list_communities()` — id, label, size.
- `community_summary(community_id)` — full summary + papers + atoms.

**Meta + escape hatch:**
- `list_missing_details()` — open implementation questions.
- `graph_stats()` — counts, target_paper_id, schema_version.
- `schema_doc()` — `research/SCHEMA.md` verbatim.
- `graph_sql(sql, params=None, limit=100)` — read-only SELECT/WITH. Refuses anything else. The escape hatch when the structured tools don't fit.

**Token efficiency rules** (v0.2):
- `query_chunks` and `paper_text` are snippet-first.
- `query_chunks` diversifies by `max_per_paper`.
- Only indexed chunks (`is_indexed=1`) participate in search.
- `graph_sql` truncates to 100 rows by default; sets `truncated=true` if more exist.

**Vector search mechanics** (`db.py::query_chunks`):
1. Tokenize the query (alphanumeric, len > 2).
2. FTS5 query: top `limit*3` results ordered by BM25.
3. If `vec_loaded`, embed the query with bge-small, KNN over `chunks_vec` with `MATCH ? AND k = ?` (sqlite-vec requires explicit `k=`).
4. Combine: BM25 contributes `-score + 0.2*quality`; vec contributes `-distance + 0.2*quality`.
5. Diversify (`_diversity_rerank`): drop near-duplicates by paper_id, cap to `max_per_paper`.
6. Return `{"results": [...], "truncated": bool}`.

**Known issues:**
- `equation_lookup` is a stub (mentioned above). We have `equations` table populated but no client.
- `graph_sql` is technically read-only but uses string prefix matching (`startswith("select"|"with")`). A maliciously crafted query with comments could potentially bypass. Acceptable because the DB is local + read-only-mounted; not acceptable if exposed over a network.
- Cold start time scales with embedder load (~1.5 s for bge-small on first call). The model is held in module state thereafter.
- `paragraph_ids` filter accepts a list of ids; we don't validate that they all belong to the requested `paper_id`. Mismatched ids silently return empty.

---

## 6. LLM backend — using your Claude Code session

**File:** `cli/src/paper_compiler_cli/llm.py`

The CLI runs LLM calls for: edge classification (residual), atom extraction, community summarization. Backend priority:

1. **`ANTHROPIC_API_KEY` set** → direct `anthropic` SDK call. Fastest, most metered.
2. **`claude` CLI on PATH** → headless subprocess `claude -p --output-format json --tools "" --no-session-persistence --disable-slash-commands --system-prompt "..." "<user>"`. **Uses Claude Code subscription auth — no API key required.**
3. **Neither available** → returns `None`; callers fall back to heuristic only.

This is the "reuse your subscription" path. When the CLI runs inside a forked subagent of a Claude Code session, the `claude` CLI is on PATH and uses the same OAuth keychain entry the session uses.

`call_llm(cfg, system, user, model=None, max_tokens=400, json_schema=None)` is the single entry point. `parse_json_object(text)` extracts the first `{...}` block from the response (claude CLI often wraps JSON in markdown code fences).

**Known issues:**
- `claude -p` is slower than the direct SDK (each call boots the CLI). For a typical compile with 30 atom-extraction + 8 classifier + 12 community calls, this adds 30–60 s wall time.
- The CLI's stdout `result` field contains the response text but is JSON-wrapped; we have to strip the envelope. Format may change.
- We don't pass `--max-budget-usd` per call. Could be a guardrail.
- If both `ANTHROPIC_API_KEY` and the CLI are available, we silently prefer the SDK. Documented in the function docstring.

---

## 7. Skills — Claude-side surface

**Files:** `plugin-scaffold/skills/*/SKILL.md`.

Six skills total in v0.2:

| Skill | Trigger | Mode |
|---|---|---|
| `build-research-context` | "compile this paper", "build research context", `/build-research-context arxiv:…` | manual, forked, ≤ 150 line body + invokes CLI |
| `use-research-context` | implementation work in a repo with `research/` | auto-invoke, ≤ 100 line body + 6 task playbooks in `references/` |
| `audit-against-research` | "audit my code", "is this faithful", PR review | auto-invoke, ≤ 80 line body + `references/audit-checklist.md` |
| `wiki-query` | "ask the wiki", "what does the corpus say", open-ended questions about the paper/neighborhood | auto-invoke, ≤ 80 line body + 2 references (`promotion-rules.md`, `log-format.md`) |
| `wiki-ingest` | "ingest this paper", "add to the corpus" | manual, forked, calls `paper-compiler ingest` |
| `wiki-lint` | "lint the wiki", "health check" | manual, forked, warn-only |

Designed against the Anthropic spec (`code.claude.com/docs/en/skills`):
- Bodies ≤ 500 lines (most well under).
- `description` < 1,536 chars combined with `when_to_use`. Trigger phrases come first.
- Heavy task-specific guidance lives in `references/` per-skill, loaded only when needed.
- Forked skills set `context: fork` + `agent: general-purpose`.
- `paths:` globs auto-activate skills only in repos with `research/`.
- `allowed-tools:` enumerates exactly the MCP tools each skill may call (without permission prompts).

### 7.1 Per-skill references

`use-research-context/references/`:
- `implementing-architecture.md`
- `implementing-loss.md`
- `implementing-dataset.md`
- `implementing-eval.md`
- `implementing-baseline.md`
- `debugging-mismatch.md`

Each is ~120–180 lines: the exact MCP call sequence for that sub-task, watch-out list, and a verification checklist. The point is to teach Claude *which* tool to call *when*, not to inline the whole catalog into the SKILL body.

`audit-against-research/references/audit-checklist.md` — per-category audit recipes (architecture, loss, dataset, preprocessing, evaluation, baseline, optimizer, hyperparameter).

`wiki-query/references/`:
- `promotion-rules.md` — when to write an `answers/<slug>.md`.
- `log-format.md` — `log.md` entry shape.

**Known issues:**
- Some references repeat each other on the watch-out lists (e.g. "check verbatim vs paraphrased" in multiple files). Minor duplication.
- `references/` are loaded by Claude reading them mid-session; they're not auto-injected. The skill body has to explicitly point to them. We do this.
- `paths:` activation is OR-ed across the listed globs. We list `research/research.md` and `research/research.db` to make sure both compiled and DB-only states activate the skill.
- `agent: general-purpose` for forked skills means they don't get specialized agent prompts (Explore/Plan). For build/ingest/lint that's correct — they're orchestration tasks, not analysis tasks.

---

## 8. CLI surface

Entry point: `${CLAUDE_PLUGIN_ROOT}/cli/bin/paper-compiler` (a thin shim that adds `cli/src` to `sys.path`).

Subcommands:

```
paper-compiler resolve <input>
    → JSON candidates with paper_id, title, year, authors, confidence.

paper-compiler parse <input> --out paper.json
    → resolve + acquire + parse → IR JSON. Useful for debugging the parser.

paper-compiler build <paper-id-or-input> --out research/ [flags]
    Full pipeline (stages 1–9).
    Flags:
      --refresh             invalidate cache
      --max-depth N         (default 2)
      --max-papers N        (default 200)
      --top-k N             (default 20)  depth-2 papers per top-K depth-1
      --atom-papers N       (default 10)  cited papers to extract atoms from
      --max-s2-requests N   (default 500)
      --max-wall-seconds N  (default 1200)
      --classifier-llm-calls N  (default 50)
      --atom-llm-calls N    (default 80)
      --no-llm              heuristics only
      --research-md-tokens N    (default 8000)
      --config path         override config.toml location

paper-compiler ingest <paper-id-or-input> --research-dir research/ [--force]
    Add one more paper to an existing compiled corpus.
    Cheap (1–5 min); reuses existing DB + neighborhood.

paper-compiler cache {prune,info} [--older-than 90d]
    Not implemented in v1 — stub.
```

**Config:** `paper-compiler.toml` in cwd or `~/.config/paper-compiler/config.toml`. All compile flags override config values. `.env` in cwd is auto-loaded for `SEMANTIC_SCHOLAR_API_KEY` and `ANTHROPIC_API_KEY`.

**Known issues:**
- `cache prune` isn't implemented. The cache grows monotonically. Disk impact ~50–200 MB per compiled paper (most of it parsed PDF/TeX).
- `parse` subcommand returns the IR for the target paper only, not the neighborhood. Useful for debugging but not for re-using parsed results.
- Multiple S2 keys aren't supported (single `[s2] api_key` slot).

---

## 9. Plugin layout

```
plugin-scaffold/
├── .claude-plugin/
│   ├── plugin.json              # manifest
│   └── marketplace.json
├── .mcp.json                    # declares the MCP server
├── CLAUDE.md                    # plugin-level Claude instructions
├── CHANGELOG.md
├── README.md
├── cli/
│   ├── bin/paper-compiler       # exec shim
│   ├── pyproject.toml
│   ├── README.md
│   └── src/paper_compiler_cli/
│       ├── __init__.py / __main__.py / cli.py / config.py / cache.py
│       ├── s2_client.py / resolve.py / acquire.py
│       ├── parse/ {__init__.py, tex.py, pdf.py}
│       ├── expand.py
│       ├── classify/ {__init__.py, heuristic.py, llm.py, edge.py}
│       ├── atoms/ {__init__.py, extract.py, dedup.py}
│       ├── score.py
│       ├── text_utils.py        # shared chunking/quality
│       ├── graph_db.py          # sqlite schema + ingest functions
│       ├── communities.py
│       ├── compile.py           # orchestrator
│       ├── ingest.py            # incremental add
│       ├── llm.py               # backend abstraction
│       └── render/
│           ├── research_md.py / missing_details.py / evidence_files.py
│           ├── graph_json.py / build_manifest.py / schema_doc.py
│           ├── wiki.py / wiki_log.py / wiki_schema_doc.py / embeddings.py
├── server/
│   ├── pyproject.toml
│   └── src/paper_compiler_mcp/
│       ├── __init__.py
│       ├── server.py            # FastMCP entry; 15 tool wrappers
│       ├── graph.py             # legacy JSON-graph fallback
│       └── db.py                # all SQL/vec/FTS5 logic
├── skills/
│   ├── build-research-context/SKILL.md
│   ├── use-research-context/
│   │   ├── SKILL.md
│   │   └── references/  (6 task playbooks)
│   ├── audit-against-research/
│   │   ├── SKILL.md
│   │   └── references/audit-checklist.md
│   ├── wiki-query/
│   │   ├── SKILL.md
│   │   └── references/ {promotion-rules.md, log-format.md}
│   ├── wiki-ingest/SKILL.md
│   └── wiki-lint/SKILL.md
├── hooks/
│   └── hooks.json               # PreToolUse warn-only hook
└── scripts/
    └── check-assumptions.sh
```

`.mcp.json` declares the server:
```json
{
  "mcpServers": {
    "paper-compiler": {
      "command": "python",
      "args": ["-m", "paper_compiler_mcp.server"],
      "env": {
        "PYTHONPATH": "${CLAUDE_PLUGIN_ROOT}/server/src",
        "PAPER_COMPILER_RESEARCH_DIR": "${PWD}/research"
      }
    }
  }
}
```

The hook (`hooks/hooks.json` + `scripts/check-assumptions.sh`) is **warn-only**: on every Write/Edit, it greps `missing-details.md` for keywords that appear in the file being edited and emits a stderr warning if the file touches an unacknowledged assumption.

---

## 10. Build numbers — verified on JEPA (arxiv:2603.19312)

Command:
```bash
paper-compiler build arxiv:2603.19312 --out research/ --refresh \
  --max-depth 2 --max-papers 80 --top-k 12 \
  --atom-papers 10 --classifier-llm-calls 8 --atom-llm-calls 30
```

Output:
- Wall time: 1052 s (~18 min).
- References attempted: 52; resolved: 29 (**55.8% coverage**).
- Neighborhood: **256 papers** (134 acquired + parsed with full text, 122 metadata-only).
- Chunks: 14,228 total → 5,672 indexed (40% retention).
- Atoms extracted: **153** (post-dedup), across 9 categories.
- Atoms by category: 46 architecture, 28 hyperparameter, 25 training_trick, 13 preprocessing, 12 evaluation, 11 dataset, 8 baseline, 6 loss, 4 optimizer.
- Distinct defining papers for atoms: **14**.
- Edges classified: 42 (8 via LLM, 34 heuristic).
- Communities: **3** ("JEPA World Models" 22 papers, "Visual World Models Planning" 4, "Graph-Based Adaptive Robot Dynamics" 3).
- Wiki articles: **433** (152 atoms + 256 papers + 3 communities + index + SCHEMA + log + 19 evidence files).
- DB size: 28.9 MB.

LLM backend used: `claude_cli` (no `ANTHROPIC_API_KEY` set, used Claude Code subscription auth via `claude -p`).

---

## 11. End-to-end usage

Setup (one-time):

```bash
# Install
pip install -e plugin-scaffold/cli[graph,indexes] \
            -e plugin-scaffold/server[vector]

# Persist S2 key (recommended) — survives shell restarts
echo 'SEMANTIC_SCHOLAR_API_KEY=s2k-...' >> .env
```

Per-paper:

```bash
# In the repo where you'll implement the paper
mkdir -p ~/work/paper-impl && cd ~/work/paper-impl && git init

# Launch Claude Code with the plugin
claude --plugin-dir /path/to/plugin-scaffold
```

Inside Claude Code:

```
/paper-compiler:build-research-context arxiv:2603.19312
```

Wait 5–20 minutes. The skill runs in a forked subagent; the main session is free.

After the build, ask:

```
Implement the CEM planner from this paper. Use the graph DB.
```

`use-research-context` auto-activates, consults `references/implementing-loss.md` (CEM is an optimizer-category atom), pulls atoms via `trace_dependency("optimizer")`, gets evidence, queries `paper_text` for the CEM defining paper's full text, writes the planner with citations.

For open-ended exploration:

```
/paper-compiler:wiki-query What's the relationship between SIGReg and InfoNCE in this corpus?
```

`wiki-query` synthesizes an answer with `[[wikilinks]]`, and if it touched ≥ 2 atoms in ≥ 2 communities, promotes it to `research/wiki/answers/sigreg-vs-infonce.md`.

For adding more context:

```
/paper-compiler:wiki-ingest arxiv:2305.18290
```

Adds DPO (or whatever paper) to the existing corpus. Communities are recomputed; wiki refreshed; log appended.

For health-checks:

```
/paper-compiler:wiki-lint
```

Generates `wiki/lint-report.md`.

For PR review:

```
/paper-compiler:audit-against-research
```

Generates `audit-report.md` with per-atom verdicts.

---

## 12. Token efficiency

The system is designed to **replace** web search for paper-specific facts. Per-query token cost target: ≤ 2K tokens output by MCP tools, ≤ 20K total context spent on the paper context across a session.

Strategies in place:
- **Snippet-first.** `query_chunks` and `paper_text` return 240-char snippets by default. Full text requires explicit `full=True`.
- **Diversification.** `max_per_paper=2` prevents one mega-paper from crowding out the rest.
- **Indexed-only retrieval.** ~60% of chunks (tables, captions, layout) are excluded from FTS5 + vec0.
- **Per-tool budgets.** `query_chunks` returns ≤ `limit*2` candidates pre-rerank, ≤ `limit` post.
- **Per-skill `references/`** are loaded only when the skill body says "see references/X.md" — Claude doesn't preload them.
- **Compile-time LLM caps.** `--classifier-llm-calls` and `--atom-llm-calls` bound the LLM-on-CLI cost.

Empirically on JEPA, a five-turn implementation session ("plan", "implement CEM", "implement loss", "audit", "wiki-query about a subtlety") consumes ~25K MCP-result tokens — about 6× less than the equivalent web-search workflow that would re-read the paper PDF on every turn.

**Known issues:**
- We don't enforce a global per-call byte budget; `paper_text(full=True)` on a long paper can return ~30 KB. Mitigated by the snippet-first default but not eliminated.
- The reranker is BM25 + cosine + quality prior. It's not learned and not query-aware beyond keyword matching.

---

## 13. Configuration surface

All flags and config keys honored in v1:

`paper-compiler.toml`:
```toml
[s2]
api_key = "..."
rate_limit_rps = 1.0

[compile]
max_depth = 2
max_papers = 200
max_s2_requests = 500
max_wall_seconds = 1200
classifier_llm_max_calls = 50
atom_llm_max_calls = 80
expand_top_k = 20
atom_paper_count = 10           # new in v0.2

[parser]
prefer = "tex"
pdf_backend = "marker"

[output]
research_dir = "research"
research_md_max_tokens = 8000

[cache]
dir = "~/.cache/paper-compiler"
ttl_metadata_days = 30

[llm]
provider = "anthropic"
classifier_model = "claude-haiku-4-5"
atom_model = "claude-haiku-4-5"
```

Env: `SEMANTIC_SCHOLAR_API_KEY`, `ANTHROPIC_API_KEY` (optional — see §6), `PAPER_COMPILER_RESEARCH_DIR` (set by `.mcp.json`).

---

## 14. Limitations summary (the honest list)

Aggregated from each section above; one stop-shop for what to expect.

**Acquisition / parsing:**
- 3% of papers fail to acquire (HTTP, redirects, closed access). Marker is off by default.
- TeX parser is fragile on heavy macro use; ~5% of acquired TeX papers yield < 5 parsed sections.
- Tables and figure contents are not retained (only captions).
- No OCR on diagrams.

**Coverage:**
- Reference resolution averages **45–65%**. Workshop papers, software releases, technical reports remain unresolved.
- S2 search-based resolution can pick a wrong same-title paper despite author scoring.
- Depth-2 priority inheritance is heuristic.

**Atom extraction:**
- Atom-id reshuffle on recompile breaks wiki-answer references. **v0.3 blocker.**
- LLM extraction quality is bimodal.
- Multi-paper extraction (`--atom-papers 10`) skews the atom distribution toward citation-rich subfields.
- Heuristic name-spotting still produces a few misclassifications.

**Edge classification:**
- Hand-labelled accuracy ~72% per role (below 75% target).
- Heuristic confidence can be confidently wrong without LLM rescue.
- Multi-label is stored but downstream tools use only `best_role`.

**Chunking / retrieval:**
- Quality thresholds are fixed, not learned.
- Tables that carry implementation signal (ablation hyperparameters) are excluded by the digit-ratio rule.
- Overlap is fixed; not adaptive to paragraph length.
- `graph_sql` is SELECT/WITH-only but uses prefix matching (acceptable for local read-only DB; not network-safe).

**Communities:**
- Louvain resolution = 1.4 magic number, not tuned across corpora.
- Recompute is wholesale on every compile/ingest. Fine for ≤ 500 papers.

**Wiki:**
- Articles are regenerated wholesale; hand-edits to generated files are lost.
- `wiki-lint` is structural, not semantic. Contradictions across papers are not detected.
- Promotion rule (≥ 2 atoms in ≥ 2 communities) is heuristic.

**MCP server:**
- `equation_lookup` is a stub.
- Cold-start with embedder loads ~1.5 s.
- No paragraph_id validation against requested paper_id.

**CLI:**
- `cache prune` not implemented.
- No multi-key support for S2.

**Skills:**
- Some `references/` content is repetitive across files.
- `paths:` activation is OR-ed; can over-trigger on repos with stale `research/` dirs.

**Costs:**
- A typical compile (100–200 papers, --atom-papers 10) uses ~50 LLM calls. With `claude_cli` backend, this draws from your Claude Code subscription Agent SDK budget (introduced 2026-06).
- Cache grows monotonically; expect 50–200 MB per compiled paper.

---

## 15. What this hasn't done (v2 candidates)

In order of estimated impact:

1. **Stable atom ids** — deterministic from `(category, canonical_name)`. Unblocks wiki-answer reuse across compiles.
2. **Semantic lint** — LLM pass that finds contradictions across answer pages and between answer pages and atoms.
3. **Delta community detection** — don't rebuild communities on every ingest.
4. **Multi-paper compile** — one shared wiki/DB across N target papers (PaperBench-style).
5. **Re-ingest answers into chunks_fts** — so `query_chunks` can match prior synthesized answers.
6. **Equation indexing** — populate `chunks_vec` over LaTeX strings; wire `equation_lookup`.
7. **Adaptive chunk size** — function of paragraph length and section type.
8. **Learned reranker** — fine-tune on labelled query-chunk pairs from compiled corpora.
9. **HTML wiki viewer** — single-page browser for the wiki (Obsidian works today but isn't shippable).
10. **Hook auto-fix** — wiki-lint moves from warn-only to fix-with-confirmation.
11. **PaperBench eval** — actually run the 60-run study from `docs/05`.

---

## 16. Verification — running the gates locally

The acceptance gates that the JEPA build passed (and that any future change should pass):

```bash
DB=research/research.db

# ≥ 35 atoms
sqlite3 $DB "SELECT COUNT(*) FROM atoms;"           # expect 35+

# ≥ 6 distinct defining papers
sqlite3 $DB "SELECT COUNT(DISTINCT defined_by_paper_id) FROM atoms;"

# 3–8 communities
sqlite3 $DB "SELECT COUNT(*) FROM communities;"

# Top-3 longest indexed chunks are prose
sqlite3 $DB "SELECT length(text), substr(text,1,150) FROM chunks
             WHERE is_indexed=1 ORDER BY length(text) DESC LIMIT 3;"

# Wiki filenames are not doubled
ls research/wiki/atoms/ | head -5    # expect atom-001.md, not atom-atom-001.md

# Wiki log + schema exist
head research/wiki/log.md
head research/wiki/SCHEMA.md

# Indexed vs total chunks
sqlite3 $DB "SELECT is_indexed, COUNT(*) FROM chunks GROUP BY is_indexed;"
```

Live MCP smoke test:

```python
from paper_compiler_mcp.db import open_ro, query_chunks, neighborhood_subgraph, shortest_paths
from pathlib import Path

conn, vec = open_ro(Path("research/research.db"))

# Hybrid BM25 + vec
print(query_chunks(conn, vec, "cross-entropy method optimization", limit=4))

# Graph traversal
print(neighborhood_subgraph(conn, "atom-011", hops=2))
print(shortest_paths(conn, "atom-011", "s2:5c5e69387020d7ca7d49487ca841958dc5e08ce6"))
```

---

## 17. The deliberate trades

A short list of choices that are correct *for v1* but might look like bugs:

- **Plane separation.** The MCP server can't trigger an ingest. This is intentional — predictable read-only runtime, expensive writes only in the forked subagent.
- **Atom-id sequential.** Stable cross-compile ids would require interning; deferred to v0.3.
- **Wiki articles regenerated wholesale.** Hand-edits lost. The trade is determinism: the wiki is always a function of the DB.
- **Tables excluded from retrieval.** Some are useful; almost all are noise. The right answer is per-table classification (v2).
- **Per-paper diversification cap of 2.** Sometimes a single paper *is* the answer and gets clipped. Workaround: `paper_text(paper_id, …)` directly.
- **No web search fallback.** When a fact isn't in the corpus, the answer is "ingest the missing paper", not "search Google". Token-efficient by design.
- **Heuristic > LLM where it works.** Classifier and atom extraction both fall through to heuristic on LLM failure rather than retrying. Avoids retry loops; loses precision.

---

## 18. Glossary

- **Atom** — a reusable implementation component (architecture block, loss formulation, dataset, etc.).
- **Brief** — `research/research.md`, the ≤ 8000-token human-readable summary.
- **Chunk** — a paragraph (or paragraph-window) of text. Unit of retrieval. Has `chunk_id`, `is_indexed`, `quality`.
- **Citation edge role** — one of the 11 labels in PRD §12 (`architecture_dependency`, `loss_function_dependency`, …).
- **Community** — a cluster of papers detected by Louvain over the citation + atom-shared graph.
- **Compile** — full pipeline run: stages 1–9.
- **Defining paper** — the paper that introduces an atom (`defined_by_paper_id`). May be the target or a cited paper.
- **Evidence span** — a `(paper_id, section_id, verbatim_text)` triple backing an atom claim.
- **Frontier policy** — the priority + budget logic that picks which references to expand.
- **Graph RAG** — retrieval over the implementation atom graph + chunk text, using sqlite-vec + FTS5.
- **Hybrid search** — BM25 (lexical) + vector cosine (semantic) merged in `query_chunks`.
- **IR** — intermediate representation; the parsed `Paper` pydantic model.
- **llm-wiki** — Karpathy's notion of an LLM-maintained markdown knowledge base. Implemented here as `research/wiki/`.
- **MCP tool** — a function exposed by the `paper-compiler` MCP server, named `mcp__paper-compiler__<tool>`.
- **Promotion** — saving a `wiki-query` answer as `wiki/answers/<slug>.md`.
- **Skill** — a `SKILL.md` file with YAML frontmatter that teaches Claude when/how to do something.
- **Snippet-first** — default response shape for chunk-retrieving tools: short preview + chunk_id. Full text on demand.
- **Subgraph** — output of `neighborhood_subgraph`: rooted, labeled, with `via_atoms` bridges.

---

*End of v1 build document. Single source of truth for what is implemented today and what is known to be wrong. Update on every v0.x release.*
