# Architecture — System Design and Data Model

**Companion to:** `01-PRD.md`, `03-claude-code-plugin-guide.md`.
**Purpose:** the technical blueprint. How the compile pipeline is wired, what the data structures look like, where the boundaries are, and what to build first.

---

## 1. The big picture in one diagram

```
                ┌────────────────────────────────────────────┐
                │              Claude Code session            │
                │                                              │
                │   skills:                                    │
                │     • use-research-context                   │
                │     • audit-against-research                 │
                │   tools: mcp__paper-compiler__*              │
                └────────┬─────────────────────────────▲──────┘
                         │ queries                      │ structured evidence
                         ▼                              │
                ┌────────────────────────────────────────────┐
                │            paper-compiler MCP server         │
                │      (reads research/ at session start)      │
                └────────┬─────────────────────────────────────┘
                         │ load
                         ▼
                ┌────────────────────────────────────────────┐
                │              research/  (on disk)             │
                │   • research.md                                │
                │   • missing-details.md                         │
                │   • graph.json                                 │
                │   • evidence/<atom-id>.md                      │
                │   • build-manifest.json                        │
                └────────▲─────────────────────────────────────┘
                         │ writes
                         │
                ┌────────────────────────────────────────────┐
                │     build-research-context skill (subagent)   │
                │              (context: fork)                  │
                │  invokes:                                     │
                └────────┬─────────────────────────────────────┘
                         │
                         ▼
                ┌────────────────────────────────────────────┐
                │           paper-compiler CLI (compile)        │
                │   stages:                                     │
                │     1. Resolve                                │
                │     2. Acquire                                │
                │     3. Parse → IR                             │
                │     4. Expand neighborhood                    │
                │     5. Classify citation edges                │
                │     6. Build atom graph                       │
                │     7. Score and rank                         │
                │     8. Index for query                        │
                │     9. Render outputs                         │
                └────────┬───────────────────────┬─────────────┘
                         │                       │
                         ▼                       ▼
                ┌──────────────────┐   ┌──────────────────────┐
                │ Semantic Scholar │   │ Local doc parsers    │
                │ (Graph + Recs)   │   │ (TeX + GROBID + ...) │
                └──────────────────┘   └──────────────────────┘
```

Three runtime planes:

1. **Compile plane** — runs once per paper. Heavyweight. Writes to `research/`. Owned by the subagent.
2. **Storage plane** — `research/` directory. Plain files. Committed to the user's repo.
3. **Query plane** — MCP server + skills. Read-only. Owns the user-visible interaction.

Keep these planes strictly separate. The MCP server never writes. The CLI never serves requests.

---

## 2. Component inventory

| Component | Lives in | Language | Owns |
|---|---|---|---|
| Plugin shell | `paper-compiler/` | (config) | Skills, hooks, manifest |
| CLI compiler | `cli/` | Python | The entire compile pipeline |
| MCP server | `server/` | Python | Runtime query surface |
| Skills | `skills/*/SKILL.md` | Markdown | Workflow steering |
| Hooks | `hooks/hooks.json` + `scripts/` | shell / python | Guardrails |
| Storage | `research/` (per user repo) | JSON/MD | Compiled artifacts |

Language choice: **Python everywhere**, because the parser ecosystem (GROBID clients, PDF libraries, S2 SDKs, MCP SDK, vector indexes) is strongest there. If you find a compelling reason for TypeScript in one component later, swap that component — the contracts between components are file-based, language-agnostic JSON.

---

## 3. Stage-by-stage compile pipeline

Nine stages. Each writes to disk. Each is independently resumable (idempotent + cached). Do not merge stages even if it looks like you can.

### Stage 1 — Resolve

**Input:** raw user input (arXiv ID, DOI, S2 ID, URL, local path).
**Output:** canonical `paper_id` (S2 ID), `external_ids`, basic metadata.
**Side effects:** none.

Implementation:

- arXiv ID → `GET /graph/v1/paper/ARXIV:<id>`
- DOI → `GET /graph/v1/paper/DOI:<doi>`
- S2 ID → `GET /graph/v1/paper/<id>`
- Local PDF / TeX → extract title + first-page bibliographic data, then `GET /graph/v1/paper/search?query=<title>` and disambiguate by author/year.

If multiple candidates pass the threshold, return all of them and let the build skill ask the user.

### Stage 2 — Acquire

**Input:** `paper_id`, `external_ids`.
**Output:** local copy of the paper's source — TeX archive preferred, PDF fallback.
**Side effects:** writes to a content-addressed cache (`~/.cache/paper-compiler/papers/<paper-id>/`).

Acquisition order:

1. **arXiv source tarball** (`https://arxiv.org/e-print/<id>`) if the paper has an arXiv ID. Almost always the best source for ML papers.
2. **`openAccessPdf.url` from S2** if no arXiv.
3. **User-provided local file** if both above fail.

If none of the above succeed, mark the paper as `unacquirable` and continue. (Many citation-neighborhood papers will be unacquirable — that's fine; we still have their metadata.)

### Stage 3 — Parse → IR

**Input:** local TeX archive or PDF.
**Output:** IR JSON conforming to the schema in §4.
**Side effects:** writes to `~/.cache/paper-compiler/parsed/<paper-id>.json`.

Parsing strategy:

- **TeX path (preferred for ML papers):** Use a TeX-aware parser. Pandoc + custom citation/equation extractors is one workable choice. The output is structurally cleaner than any PDF parse.
- **PDF path (fallback):** GROBID for structure + bibliography. A layout-aware parser (Nougat, Marker, or MinerU — pick one in week 4) for math and tables.

The IR is the **only** representation the rest of the pipeline reads. Stages 4–9 never look at the source PDF/TeX again.

### Stage 4 — Expand neighborhood

**Input:** target paper IR, S2 references.
**Output:** a set of papers in the citation neighborhood, each with metadata, optional IR.
**Side effects:** S2 API calls (rate-limited, batched), cache writes.

Frontier policy:

1. Start with the target paper's direct references (depth 1).
2. For each reference, compute an **expansion priority** from the target paper's IR:
   - Section type of the citation (Method = high, Experiments = high, Related Work = low).
   - Proximity to equations, algorithms, table captions (high).
   - Repeated citation across multiple sections (high).
   - S2 influential-citation flag for this edge (medium).
3. Expand the top-K (default K=20) references to depth 2.
4. At depth 2, only expand references that are themselves classified as implementation-critical from the depth-1 paper (we now have a classifier — see stage 5 — and we run it eagerly during expansion).
5. Hard caps: max depth 3, max papers 200, max S2 requests 500, max wall time 20 minutes.

This is the expansion algorithm that prevents citation explosion. **Do not** uniformly expand all references — you'll burn the budget on related-work papers.

Use S2 batch endpoints (`POST /paper/batch`) to fetch metadata for up to 500 IDs per call.

### Stage 5 — Classify citation edges

**Input:** every `(target_paper, cited_paper)` edge with its citation context from the IR.
**Output:** a list of `(role, confidence)` tuples per edge.
**Side effects:** none.

Classifier architecture (v1, hybrid):

1. **Heuristic pass.** Fast, rule-based, runs on every edge:
   - Section type → narrow the candidate roles. (Methods → architecture / loss / preprocessing. Experiments → dataset / evaluation / baseline. Related Work → related_work_only.)
   - Adjacent equation? → boost architecture / loss / theoretical_assumption.
   - Adjacent table? → boost baseline / evaluation_protocol.
   - Cited in caption of an algorithm box? → architecture or optimizer.
   - Bibliographic style of the cited paper (dataset paper, software paper, theory paper) → strong prior.
2. **LLM pass for the residual.** For edges the heuristic returns low-confidence on, call an LLM with the citation context paragraph and the candidate roles. Use temperature 0. Cap at ~50 LLM calls per compile.

Output schema:

```json
{
  "edge_id": "target_paper_id::cited_paper_id::occurrence_idx",
  "roles": [
    { "label": "loss_function_dependency", "confidence": 0.86 },
    { "label": "theoretical_assumption", "confidence": 0.21 }
  ],
  "context": "...the contrastive objective of [12] is modified by...",
  "section_id": "sec-3",
  "section_type": "method",
  "nearby_equation_ids": ["eq-3"],
  "nearby_algorithm_ids": [],
  "nearby_table_ids": []
}
```

Replaceability: a v2 fine-tuned classifier should be a drop-in. The interface is "edge in, ranked roles out."

### Stage 6 — Build atom graph

**Input:** classified edges + IRs.
**Output:** the implementation atom graph (§5).
**Side effects:** none.

Atom extraction is rule-based + LLM:

1. From the target paper's Method section, extract candidate atoms:
   - Each named architecture component → atom (category `architecture`).
   - Each loss formula → atom (category `loss`).
   - Each preprocessing step → atom (`preprocessing`).
   - etc.
2. For each atom, link to the **defining paper** via the citation edge classification:
   - If the atom's surrounding text cites a paper with role `architecture_dependency` (or matching role for the category), that's the defining paper.
   - If no citation, the atom is defined by the target paper itself.
3. Link atoms to evidence spans:
   - The text region in the target paper where the atom is mentioned.
   - The text region in the defining paper where the atom is introduced.

### Stage 7 — Score and rank

**Input:** atom graph.
**Output:** per-paper scores; per-atom priority; recommended implementation order.
**Side effects:** none.

Two scores per paper:

- `scholarly_influence = w1*log(citation_count+1) + w2*influential_citation_count + w3*recency + w4*recommendation_similarity`
- `implementation_influence = sum over atoms it defines of atom_priority + count of method-section citations + equation_proximity_boost + repeated_citation_boost`

Combined rank:

- `rank = 0.7 * implementation_influence + 0.3 * scholarly_influence` (tunable; the implementation term dominates by design).

Implementation order:

- Topological sort of atoms by dependency. Architecture atoms before loss atoms that consume them; loss atoms before training-loop atoms; dataset atoms early; evaluation atoms last.
- Where the topology is ambiguous, break ties by atom priority.

### Stage 8 — Index for query

**Input:** atom graph + IRs.
**Output:** in-memory indexes for the MCP server.
**Side effects:** writes `research/graph.json` (everything needed to reconstruct).

Indexes:

- **BM25** index over atom names and descriptions.
- **Vector** index over atom descriptions and evidence spans. Use a small sentence-embedding model that runs locally — SPECTER2 if you want scholarly-aware embeddings, otherwise a small general one. Cache embeddings on disk.
- **Structured graph** kept in memory as a Python `dict` of dicts; persisted as JSON.

### Stage 9 — Render outputs

**Input:** atom graph, scores, indexes.
**Output:** `research/research.md`, `research/missing-details.md`, `research/evidence/*.md`, `research/build-manifest.json`.
**Side effects:** writes to user's repo.

Rendering rules:

- `research.md` ≤ 8,000 tokens. If you blow the budget, push to evidence files.
- Every atom in `research.md` has a stable ID. Stable IDs are how Claude Code references atoms in code comments.
- `missing-details.md` is a numbered list. Each item names the gap, the candidate options, and a suggested default.
- `evidence/<atom-id>.md` contains the verbatim spans, sources, and equation IDs. The MCP server returns these in `get_evidence`.

---

## 4. The IR schema (full)

```json
{
  "schema_version": "1.0",
  "paper_id": "s2:649def34f8be52c8b66281af98ae884c09aef38b",
  "external_ids": {
    "arxiv": "2310.XXXXX",
    "doi": "10.XXXX/...",
    "corpus_id": "..."
  },
  "metadata": {
    "title": "...",
    "authors": [{ "name": "...", "s2_author_id": "..." }],
    "year": 2023,
    "venue": "...",
    "abstract": "..."
  },
  "acquisition": {
    "source": "arxiv_tex",
    "fetched_at": "2026-05-17T...Z",
    "cache_path": "..."
  },
  "sections": [
    {
      "id": "sec-3",
      "title": "Method",
      "level": 1,
      "section_type": "method",
      "paragraphs": [
        {
          "id": "sec-3-p1",
          "text": "...",
          "citations": [
            {
              "marker": "[7]",
              "ref_id": "ref-7",
              "resolved_paper_id": "s2:...",
              "context_window": "..."
            }
          ],
          "equation_refs": ["eq-3"],
          "algorithm_refs": [],
          "table_refs": [],
          "figure_refs": []
        }
      ]
    }
  ],
  "equations": [
    {
      "id": "eq-3",
      "latex": "\\mathcal{L} = ...",
      "section_id": "sec-3",
      "mentioned_in": ["sec-3-p1"]
    }
  ],
  "algorithms": [
    {
      "id": "alg-1",
      "title": "Training procedure",
      "pseudocode": "...",
      "section_id": "sec-3"
    }
  ],
  "tables": [
    { "id": "tab-1", "caption": "...", "section_id": "sec-4", "rows": null }
  ],
  "figures": [
    { "id": "fig-1", "caption": "...", "section_id": "sec-3" }
  ],
  "references": [
    {
      "ref_id": "ref-7",
      "marker": "[7]",
      "raw": "Author, A. et al. (2021). Title. Venue.",
      "resolved_paper_id": "s2:...",
      "resolution_confidence": 0.97
    }
  ]
}
```

`section_type` values: `abstract`, `introduction`, `related_work`, `method`, `experiments`, `results`, `discussion`, `conclusion`, `appendix`, `other`. Classify with a tiny rule-based mapper from the section title; fall back to `other`.

---

## 5. The atom graph schema

```json
{
  "schema_version": "1.0",
  "compiled_at": "2026-05-17T...Z",
  "target_paper_id": "s2:...",
  "papers": {
    "s2:...": {
      "metadata": { ... },
      "scholarly_influence": 0.71,
      "implementation_influence": 0.93,
      "rank": 0.86,
      "acquired": true,
      "ir_path": "cache/parsed/s2-....json"
    }
  },
  "atoms": {
    "atom-001": {
      "name": "contrastive InfoNCE loss",
      "category": "loss",
      "defined_by_paper_id": "s2:...",
      "used_by_paper_ids": ["s2:target..."],
      "description": "Symmetric cross-entropy over softmax-normalized similarities.",
      "evidence_span_ids": ["ev-12", "ev-13"],
      "equation_refs": [{ "paper_id": "s2:...", "eq_id": "eq-4" }],
      "priority": 0.88,
      "dependencies": ["atom-005"]
    }
  },
  "evidence": {
    "ev-12": {
      "paper_id": "s2:...",
      "section_id": "sec-3",
      "section_type": "method",
      "verbatim_text": "...",
      "char_range": [1234, 1456],
      "supports_atom_ids": ["atom-001"]
    }
  },
  "edges": {
    "edge-001": {
      "from_paper_id": "s2:target...",
      "to_paper_id": "s2:...",
      "roles": [
        { "label": "loss_function_dependency", "confidence": 0.86 }
      ],
      "context": "...",
      "supports_atom_ids": ["atom-001"]
    }
  },
  "missing_details": [
    {
      "id": "md-001",
      "question": "Temperature schedule for the contrastive loss is not given.",
      "category": "loss",
      "options": ["fixed 0.07", "learned scalar", "annealed from 0.5 to 0.07"],
      "suggested_default": "fixed 0.07",
      "rationale": "Defining paper uses 0.07; target paper does not mention a schedule."
    }
  ],
  "implementation_order": [
    { "atom_id": "atom-005", "rationale": "..." },
    { "atom_id": "atom-001", "rationale": "..." }
  ],
  "build_stats": {
    "papers_resolved": 87,
    "papers_acquired": 62,
    "papers_parsed": 60,
    "atoms_extracted": 34,
    "evidence_spans": 128,
    "s2_requests": 142,
    "wall_time_seconds": 612
  }
}
```

This single file is the source of truth for the MCP server. `research.md` is a human-friendly view of a subset of it.

---

## 6. Caching strategy

Three caches, each content-addressed:

1. **S2 response cache** (`~/.cache/paper-compiler/s2/`) — keyed by request URL + fields. TTL 30 days for metadata, indefinite for references/citations (re-fetch on `--refresh`).
2. **Acquired-source cache** (`~/.cache/paper-compiler/papers/<paper-id>/`) — raw PDFs and TeX tarballs. Indefinite.
3. **Parsed-IR cache** (`~/.cache/paper-compiler/parsed/<paper-id>.json`) — keyed by source content hash + parser version. Indefinite; bumped when parser version changes.

`paper-compiler build --refresh` invalidates all three for the target paper but preserves them for the neighborhood (which is expensive to re-acquire).

`paper-compiler cache prune --older-than 90d` is the v1 maintenance command.

---

## 7. Concurrency and rate limits

S2 rate limit with an API key is 1 RPS per user. Budgets:

- **Resolve / metadata fetch:** use `POST /paper/batch` with up to 500 IDs. One batch call per round of expansion.
- **References / citations endpoints:** these don't batch in the same way; use the batch paper endpoint with `fields=references` to get references for many papers at once.
- **Concurrency:** target a sustained 1 RPS. Implement a token-bucket limiter shared across all S2 callers in the CLI.
- **Backoff:** on 429, exponential backoff with jitter, max 5 retries, then mark the paper as `failed_acquisition` and continue.

Parsing parallelism: PDF/TeX parsing is CPU-bound. Use a process pool sized to `ncpu - 1`. GROBID specifically supports concurrent requests; run it as a local service.

---

## 8. Configuration surface

User-facing config in `paper-compiler.toml` (project-local) or `~/.config/paper-compiler/config.toml` (global):

```toml
[s2]
api_key = "..."
# or use SEMANTIC_SCHOLAR_API_KEY env var

[compile]
max_depth = 2
max_papers = 200
max_s2_requests = 500
max_wall_seconds = 1200
classifier_llm_max_calls = 50

[parser]
prefer = "tex"           # "tex" | "pdf"
pdf_backend = "grobid"   # "grobid" | "marker" | "nougat" | "mineru"
grobid_url = "http://localhost:8070"

[output]
research_dir = "research"
research_md_max_tokens = 8000

[cache]
dir = "~/.cache/paper-compiler"
ttl_metadata_days = 30
```

CLI flags override config; env vars override config; flags override env vars.

---

## 9. Build vs. query — what crosses the boundary

The contract between the compile plane and the query plane is **the files in `research/`**. Nothing else.

- The CLI must never call the MCP server.
- The MCP server must never trigger a compile.
- Hot-reload of the MCP server on a new compile is achieved by `mcp__paper-compiler__graph_stats` returning `compiled_at`, and the `use-research-context` skill checking it. (For v1, restart Claude Code after a compile — simpler.)

---

## 10. Failure modes and their handling

| Failure | Behaviour |
|---|---|
| S2 timeout / 5xx | Retry 3x with backoff. On final failure, mark paper `metadata_failed`, continue compile. |
| S2 rate limit (429) | Backoff with jitter; persist the limiter state across retries. |
| PDF acquisition 404 | Try next source. If exhausted, mark `unacquirable`, continue. |
| PDF parse failure | Retry once with alternate parser. If both fail, keep metadata-only entry. |
| TeX parse failure | Fall back to PDF if available. |
| LLM classifier failure | Fall back to heuristic-only classification for that edge with `confidence=0.4`. |
| Atom extraction yields zero atoms | Surface a fatal error — something is very wrong. Don't write a misleading brief. |
| `research.md` exceeds token budget | Truncate per-atom sections from lowest priority until under budget. |

Every non-fatal failure goes in `build-manifest.json` under `failures`, and an aggregate count appears in `missing-details.md`.

---

## 11. Build order (engineering)

A defensible week-by-week plan that maps to the PRD milestones:

**Weeks 1–2 — M0 Skeleton.**
- Plugin scaffold, `plugin.json`, stub skills, `.mcp.json` pointing at a stub server, `CLAUDE.md`, `README.md`.
- Test loop: `claude --plugin-dir .` confirms skills appear, MCP tools list correctly.
- CLI binary that does only `resolve` against S2.

**Weeks 3–4 — M1 Parse + IR.**
- Implement `acquire` (arXiv tarball + S2 openAccessPdf).
- Implement TeX parser (start with pandoc + custom citation/equation extractors).
- Implement PDF parser as fallback (pick GROBID first; evaluate Marker/Nougat in week 4).
- Output: IR JSON for one paper. Validate against the schema.

**Weeks 5–7 — M2 Expansion + classifier.**
- Wire S2 batch endpoints and the token-bucket limiter.
- Implement frontier policy.
- Heuristic edge classifier.
- LLM residual classifier (Anthropic API, temperature 0).
- Hand-label 100 edges from 3 papers; measure classifier accuracy.

**Weeks 8–10 — M3 Atom graph + research.md.**
- Atom extraction from method section.
- Atom → paper linking via classified edges.
- Evidence-span assembly.
- Render `research.md`, `missing-details.md`, `evidence/`.

**Weeks 11–12 — M4 MCP server.**
- Implement the nine tools in §13 of the PRD.
- BM25 + vector indexes.
- Wire the server into the plugin.
- Smoke-test against the brief written in week 10.

**Weeks 13–14 — M5 Skills + polish.**
- Finalize the three SKILL.md files.
- Hook (warn-only).
- README, marketplace.json, install instructions.
- Compile the originating paper(s) end-to-end without manual intervention.

**Weeks 15–16 — M6 Evaluation.**
- Run the A/B replication study on a 20-paper benchmark.
- Iterate on the worst failure modes.
- Decide ship vs. keep iterating.

---

## 12. Decisions to defer

- **Embedding model.** Pick in week 11; SPECTER2 if it's not too heavy, otherwise a small general-purpose model.
- **PDF parser.** Pick in week 4 after running candidates on 5 representative ML papers.
- **LLM provider for the classifier.** Default to Anthropic for consistency, but the interface should not assume.
- **Whether `audit` ever blocks vs. warns.** Default warn; revisit after week 15 based on user feedback.

Write the choice down in this doc when each decision lands.

---

## 13. What this architecture is optimized for

Three things, in order:

1. **Faithful evidence.** Every claim in `research.md` is traceable to a verbatim span in a real paper. The whole structure exists to make this cheap to do and expensive to fake.
2. **Cheap incremental compiles.** Adding a paper to an existing compiled brief should be near-free for any paper already in the neighborhood cache.
3. **Replaceable parts.** The IR, the classifier, the parsers, the embeddings, the LLM — all interchangeable behind stable JSON schemas. No piece of this should be load-bearing in a way that costs you a week to swap.

If a design decision later in the project breaks one of these three, that's the signal to back out and reconsider.
