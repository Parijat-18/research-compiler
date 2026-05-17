# PRD — Research Compiler for Claude Code

**Codename:** `paper-compiler` (working name — see Naming section)
**Document owner:** You
**Status:** Draft v0.1
**Last updated:** May 2026

---

## 1. One-line pitch

> Give this Claude Code plugin a research paper. It compiles the paper and its citation neighborhood into an implementation-ready memory that Claude Code can query while building the repo.

---

## 2. Problem

AI research papers are **compressed implementation artifacts**, not engineering specifications. The implementation details a coding agent needs — exact architecture, loss formulation, dataset preprocessing, evaluation protocol, baseline configurations, hyperparameter conventions — are typically **distributed across the citation neighborhood** rather than contained in the paper itself.

Today, when Claude Code is asked to reproduce a paper, it works from:

1. The PDF (often partially parsed).
2. Its model memory (lossy, possibly stale).
3. Whatever it can web-search at runtime (noisy, slow, not grounded in the paper's actual citations).

This produces a predictable failure mode: **plausible-looking code that silently diverges from the paper's actual method.** PaperBench (OpenAI, 2025) quantified this — the best tested agent achieved only ~21% average replication score across 20 ICML 2024 Spotlight/Oral papers decomposed into 8,316 gradable subtasks.

The core thesis of this project:

> The missing details are not absent. They are **one or two hops away** in the citation graph. A coding agent needs a **compiled citation-dependency memory**, not just the PDF.

---

## 3. Why now

Three things converged that make this feasible in 2026 and not before:

1. **Claude Code plugin architecture** (skills + subagents + MCP servers + hooks) is the right packaging primitive for this kind of compiled-context tool. A single workflow can bundle a CLI compiler, an MCP query server, and skill-level instructions that teach the planning agent how to use both.
2. **Semantic Scholar's Academic Graph + Datasets APIs** give us a usable scholarly backbone (paper resolution, references, influential-citation signals, open-access PDF discovery, recommendations, bulk dataset access).
3. **Local document parsing** (GROBID, arXiv TeX source, layout-aware PDF parsers) has matured enough to extract section-level structure, equations, algorithms, and citation contexts at acceptable quality for ML papers.

The combination — scholarly graph as the resolver, local parsing as the source-of-truth, Claude Code plugin as the delivery layer — did not exist as a deployable unit until now.

---

## 4. Target user

**Primary:** ML engineers and researchers who use Claude Code to reproduce or extend research papers — e.g. building a repo from a recent arXiv preprint, replicating a baseline for a new project, or porting a method from a paper into an existing codebase.

**Secondary:**
- Research teams maintaining internal reproductions of upstream papers.
- Independent researchers / PhD students who reproduce SOTA as part of their workflow.
- Eval/benchmark teams (PaperBench-style) wanting structured paper context as an input to their agent harnesses.

**Explicitly NOT for:**
- Literature-review writers (this is not a survey tool).
- Citation managers (Zotero/Mendeley replace this poorly).
- General-purpose paper Q&A chatbots.

---

## 5. Product principles

1. **Implementation-first, not literature-first.** Every design decision is measured against: *does this help an agent write correct code that matches the paper?* If the answer is "it helps you understand the field," that goes to the secondary tier.
2. **Evidence over memory.** The plugin must give Claude Code verifiable evidence spans (page numbers, equation refs, paper IDs), not paraphrased summaries.
3. **Compile once, query many.** Heavy work (parsing, graph expansion, classification, indexing) happens once at compile time. Runtime is read-only queries.
4. **Local-grounded, API-assisted.** Semantic Scholar resolves and accelerates the graph. The parsed local corpus is the source of truth for any implementation claim.
5. **Subagent-isolated.** Research/planning lives in subagent context. The main Claude Code session only sees the compiled brief and answers to specific queries.
6. **Honest about uncertainty.** When the paper + neighborhood don't determine a detail, the plugin says so, names the gap, and flags it as an assumption — it does not paper over it.
7. **Claude Code-native.** This is a plugin, not a separate app. It uses the platform's primitives (skills, MCP, subagents, hooks) the way they are intended to be used.

---

## 6. Scope

### 6.1 In scope (v1)

- **Input:** an arXiv ID, DOI, URL, or local PDF/TeX archive.
- **Compilation pipeline:**
  - Resolve target paper via Semantic Scholar.
  - Acquire PDF (open-access preferred) and TeX source where available.
  - Parse to a structured intermediate representation (sections, equations, algorithms, references, citation contexts, tables, figure captions).
  - Recursively expand citation neighborhood with a frontier policy bounded by implementation-criticality, depth, and budget.
  - Classify each citation edge by **implementation role** (architecture, loss, dataset, preprocessing, evaluation protocol, baseline, optimizer/training trick, theoretical assumption, ablation reference, engineering, related-work).
  - Build the **implementation atom graph** linking papers ↔ atoms ↔ evidence spans.
  - Score papers by **implementation influence** (distinct from scholarly influence).
  - Index everything (BM25 + vector + structured graph) for query.
- **Outputs:**
  - `research/research.md` — compiled implementation brief.
  - `research/missing-details.md` — open questions and assumptions.
  - `research/graph.json` — implementation atom graph.
  - `research/evidence/` — per-claim evidence spans with citations.
  - **MCP query tools** for Claude Code to interrogate the graph at runtime.
- **Claude Code integration:**
  - One installable plugin.
  - A `build` skill (manual invocation) that runs the compilation.
  - A `use` skill (auto-invokable) that guides implementation against the compiled context.
  - An `audit` skill (auto-invokable) that checks the in-progress repo against the brief.
  - A research-exploration **subagent** with `context: fork`.
  - MCP server bundled in the plugin, exposing graph/evidence query tools.

### 6.2 Out of scope (v1)

- Running experiments / training models / executing the compiled repo.
- Writing the actual implementation code (Claude Code does that — the plugin only provides context).
- Citation graph visualization UI. (The graph is queryable; a UI may come in v2.)
- Non-English papers (acceptable to limit v1 to English ML/AI papers).
- Books, long PhD theses, multi-paper monographs.
- Closed-access papers without legally available PDFs. (We rely on what Semantic Scholar's `openAccessPdf` returns or what the user has locally.)
- A hosted backend. v1 is entirely local + API.

### 6.3 Stretch goals (v1.5 / v2)

- Caching layer that lets a team share compiled corpora.
- Citation-graph visualization (lightweight HTML artifact).
- TeX-aware diff between paper claims and repo behaviour.
- Hooks that block commits when `missing-details.md` has unresolved items the code touches.
- Local Semantic Scholar dataset mirror for offline / high-volume usage.

---

## 7. User journeys

### 7.1 Journey A — "I have a paper, I want to reproduce it"

1. User clones an empty repo, installs the plugin.
2. Runs `/paper-compiler:build https://arxiv.org/abs/2310.XXXXX`.
3. Plugin invokes a subagent that compiles the paper (~5–20 min depending on neighborhood size and API rate limits).
4. Plugin writes `research/` directory with `research.md`, `missing-details.md`, graph, and evidence.
5. User reviews `research.md`, optionally edits `missing-details.md` to fix assumptions.
6. User asks Claude Code to implement. The `use` skill triggers; Claude Code reads `research.md` first, then queries the MCP server (`trace_dependency`, `find_atom`, `cite_evidence`) for any implementation decision.
7. The `audit` skill checks each new module against the brief, flags drift.

### 7.2 Journey B — "I'm adding a baseline to an existing repo"

1. User asks Claude Code to add Baseline X (paper Y) to their existing project.
2. User runs `/paper-compiler:build` with paper Y. Plugin compiles only what's new vs. cached.
3. Claude Code queries the MCP server scoped to "baseline atoms" and implements within the existing repo structure.

### 7.3 Journey C — "Audit-only: I have code, does it match the paper?"

1. User runs `/paper-compiler:build` on the paper.
2. User runs `/paper-compiler:audit src/` against the compiled brief.
3. Plugin's audit subagent diffs the implementation atoms found in `research.md` against the code's structure and flags missing/divergent components.

---

## 8. Functional requirements

### 8.1 Paper ingestion

- **FR-1.1** Accept arXiv ID, DOI, semantic-scholar paper ID, URL, or local file (PDF or `.tar.gz` TeX source).
- **FR-1.2** Resolve to canonical Semantic Scholar `paperId` and fetch metadata (title, authors, year, venue, references, citations, `openAccessPdf`, `externalIds`).
- **FR-1.3** Acquire full text. Prefer TeX source where available; fall back to PDF via `openAccessPdf`; fall back to user-provided local file.
- **FR-1.4** Parse to structured IR (see Section 11.2 for schema). Required elements: section tree, paragraphs, equations, algorithm environments, table/figure captions, inline citation markers linked to bibliography.

### 8.2 Citation expansion

- **FR-2.1** Expand references recursively up to configurable depth (default: 2 hops, max: 3).
- **FR-2.2** Apply a **frontier policy** that prioritizes implementation-critical references for expansion and prunes related-work-only papers.
- **FR-2.3** Honor a global budget (max papers fetched, max API requests, max compile time).
- **FR-2.4** Cache all S2 responses and parsed documents on disk, keyed by paper ID + content hash.
- **FR-2.5** Respect Semantic Scholar rate limits (1 RPS with API key, batch endpoints where possible — up to 500 paper IDs per `/paper/batch`).

### 8.3 Citation edge classification

- **FR-3.1** For each citation edge `(target_paper, cited_paper)`, classify by implementation role from the closed label set (see Section 12).
- **FR-3.2** Extract the textual citation context (surrounding sentences) and the section type (Method, Experiments, Related Work, etc.).
- **FR-3.3** Detect proximity to equations / algorithms / dataset descriptions / evaluation tables.
- **FR-3.4** Produce a confidence score per edge, and where multiple roles apply, return a ranked list.
- **FR-3.5** The classifier must be replaceable (heuristic v0 → LLM-based v1 → fine-tuned model v2).

### 8.4 Implementation atom graph

- **FR-4.1** Build a graph with three node types: **papers**, **implementation atoms**, **evidence spans**.
- **FR-4.2** Each atom belongs to a category (architecture, loss, dataset, preprocessing, eval, baseline, optimizer, hyperparameter, training trick).
- **FR-4.3** Each atom is linked to (a) the paper that defines it, (b) the paper(s) that use it, (c) evidence spans that support each link.
- **FR-4.4** The graph is persisted as JSON and loadable into the MCP server's memory.

### 8.5 Scoring

- **FR-5.1** Compute two scores per paper in the neighborhood:
  - **Scholarly influence:** derived from S2 metadata (citation count, influential citation count, recency, recommendation similarity to target).
  - **Implementation influence:** derived from local evidence (section placement, equation/algorithm proximity, repeated citation, count of atoms it defines).
- **FR-5.2** Implementation influence dominates ranking. Scholarly influence is a tiebreaker.

### 8.6 Outputs

- **FR-6.1** `research.md` (see Section 11.1 for template) — concise enough to fit in context, dense enough to drive implementation. Target: ≤ 8,000 tokens.
- **FR-6.2** `missing-details.md` — every unresolved implementation question, with the gap stated explicitly and a suggested assumption.
- **FR-6.3** `graph.json` — full implementation atom graph for MCP server consumption.
- **FR-6.4** `evidence/<atom-id>.md` — per-atom evidence pack (verbatim spans, source paper, page/section refs).

### 8.7 MCP server

- **FR-7.1** Bundled in the plugin, started automatically when plugin is enabled.
- **FR-7.2** Exposes the tools described in Section 13.
- **FR-7.3** Returns **structured evidence**, not raw chunks. Every response includes confidence and source citations.
- **FR-7.4** Operates entirely on the compiled local artifacts. Does not call out to S2 at query time.

### 8.8 Skills

- **FR-8.1** `build` skill: manual invocation only (`disable-model-invocation: true`), wraps the compile pipeline, runs in a subagent with `context: fork`.
- **FR-8.2** `use` skill: auto-invokable, instructs Claude Code to consult `research.md` and MCP tools before any implementation decision in a repo that has a compiled brief.
- **FR-8.3** `audit` skill: auto-invokable when Claude Code is reviewing or finishing an implementation. Cross-checks against `research.md`.

---

## 9. Non-functional requirements

- **NFR-1 — Latency:** compile time for a typical ML paper with 2-hop expansion and ~60 reference neighborhood should fit within 5–20 minutes on a developer laptop with an S2 API key.
- **NFR-2 — Budget:** default global budget = 500 S2 requests, 100 PDFs parsed, configurable.
- **NFR-3 — Footprint:** compiled artifacts for one paper should be ≤ 100 MB on disk (target ≤ 20 MB typical).
- **NFR-4 — Failure mode:** any single failed paper acquisition or parse must not abort the compile. Failed nodes are recorded with reasons in `missing-details.md` and the build proceeds.
- **NFR-5 — Determinism:** repeating a compile on the same paper with the same config should yield byte-equivalent `graph.json` modulo timestamps. (LLM-based classifiers may be temperature-zero or seeded.)
- **NFR-6 — Privacy:** no paper content is sent to a third party other than Semantic Scholar (metadata only) and the user's configured LLM provider (which is Anthropic in the Claude Code case). Local PDFs stay local.
- **NFR-7 — Idempotency:** rerunning `build` on a paper already compiled should be near-instant (cache hit) unless `--refresh` is passed.

---

## 10. Success metrics

### 10.1 Intrinsic (does the compile work?)

- **Coverage:** % of citation references in the target paper successfully resolved on Semantic Scholar. Target ≥ 90%.
- **Parse quality:** % of cited papers for which we extracted at least one usable evidence span. Target ≥ 70%.
- **Atom completeness:** for a curated set of 20 reference papers, % of "known" implementation atoms recovered. Target ≥ 80%.

### 10.2 Extrinsic (does it help Claude Code?)

- **A/B replication score:** PaperBench-style rubric scores on the same 20 papers, comparing:
  - Claude Code + target PDF only (baseline)
  - Claude Code + `research.md` only
  - Claude Code + `research.md` + MCP tools
- **Target lift:** ≥ +10 absolute percentage points from baseline to full plugin condition on average replication score.
- **Hallucination rate:** % of implementation decisions Claude Code made that contradict evidence in the brief, measured by post-hoc grading. Target reduction of ≥ 50% vs. baseline.

### 10.3 User-facing (does anyone want it?)

- 50 weekly active users by month 3 post-launch.
- ≥ 30% of users compile more than one paper.
- ≥ 4.0/5 reported "would recommend" score in a structured user survey.

---

## 11. Key output artifacts

### 11.1 `research.md` structure

```
# Research Brief: <Paper Title>

## TL;DR
- One-paragraph what-and-why
- 3–5 bullet implementation summary

## Paper identity
- Authors, venue, year
- arXiv / DOI / S2 IDs
- Code/data links (official)

## What we're implementing
- Method overview
- Required components (links to implementation atoms)

## Implementation atoms
For each atom:
- Name and category
- Defined by: <paper>
- Used by target as: <how>
- Evidence: <link to evidence/atom-id.md>
- Equations / algorithms required
- Open questions (link to missing-details.md)

## Dependency tree
- Architecture chain
- Loss chain
- Dataset chain
- Evaluation chain
- Baselines

## Suggested implementation order
1. ...
2. ...
(Driven by dependency topology)

## Where to query the graph instead of guessing
Pointers to MCP tools per topic.
```

### 11.2 Internal IR (parsed paper)

```json
{
  "paper_id": "s2:649def34...",
  "external_ids": { "arxiv": "2310.XXXXX", "doi": "10.XXXX/..." },
  "metadata": { "title": "...", "authors": [...], "year": 2023, "venue": "..." },
  "sections": [
    {
      "id": "sec-3",
      "title": "Method",
      "level": 1,
      "paragraphs": [
        {
          "id": "sec-3-p1",
          "text": "...",
          "citations": [{ "marker": "[7]", "paper_id": "...", "context_window": "..." }],
          "equation_refs": ["eq-3"],
          "algorithm_refs": []
        }
      ]
    }
  ],
  "equations": [{ "id": "eq-3", "latex": "...", "section_id": "sec-3" }],
  "algorithms": [{ "id": "alg-1", "title": "...", "pseudocode": "..." }],
  "tables": [...],
  "figures": [...],
  "references": [{ "marker": "[7]", "raw": "...", "resolved_paper_id": "..." }]
}
```

---

## 12. Citation edge label set (v1)

Coarse, closed set. Multi-label allowed.

- `architecture_dependency` — defines a model component the target uses or modifies.
- `loss_function_dependency` — defines a loss or training objective.
- `dataset_dependency` — defines a dataset the target trains or evaluates on.
- `preprocessing_dependency` — defines preprocessing / augmentation / tokenization.
- `evaluation_protocol_dependency` — defines a benchmark or evaluation procedure.
- `baseline_dependency` — used as a comparison baseline.
- `optimizer_or_training_trick` — defines an optimizer, schedule, or training trick (e.g. mixed precision, EMA).
- `theoretical_assumption` — provides a theoretical result the target relies on.
- `ablation_reference` — cited in an ablation discussion.
- `engineering_reference` — software/library/system citation (e.g. PyTorch, FlashAttention).
- `related_work_only` — background or motivation citation; no implementation impact.

The first eight are **implementation-critical**. The last three are **non-critical** for ranking but still useful for context.

---

## 13. MCP tool surface (v1)

All tools operate on the compiled local artifacts. They return structured evidence with citations.

- **`paper_summary(paper_id)`** → metadata + implementation atoms defined or used.
- **`trace_dependency(component_type)`** → for `architecture | loss | dataset | preprocessing | evaluation | baseline | optimizer`, returns the chain of papers + atoms + evidence.
- **`find_atom(query)`** → semantic + BM25 search across implementation atoms.
- **`get_evidence(atom_id)`** → all evidence spans backing the atom.
- **`list_missing_details()`** → unresolved questions / assumptions.
- **`equation_lookup(symbol_or_keyword)`** → finds equation across the corpus.
- **`compare_methods(atom_a, atom_b)`** → side-by-side evidence comparison.
- **`citation_neighbors(paper_id, role?)`** → adjacent papers, optionally filtered by edge label.
- **`graph_stats()`** → counts, depth reached, coverage, build manifest.

---

## 14. Risks and mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Citation classifier inaccuracy | High | High | Start heuristic + LLM, evaluate on hand-labelled set, iterate. Multi-label allowed. |
| S2 rate limit / outage | Med | Med | Aggressive caching, batch endpoints, Datasets API fallback. |
| Closed-access papers in neighborhood | High | Med | Use only Semantic Scholar's `openAccessPdf` + user-provided local files. Record gaps explicitly. |
| PDF parser failures on math-heavy papers | High | Med | TeX-first when available. Fall back to layout-aware PDF parser. Record failures. |
| Compile-time too long | Med | High | Frontier policy, budgets, parallelism, cache. |
| `research.md` too long for context | Med | High | Hard token budget. Push detail to MCP-queryable evidence. |
| Skill / plugin API changes in Claude Code | Low | High | Pin to a documented schema version, watch upstream changelog. |
| Project mistaken for a generic "lit review" tool | Med | Med | Position relentlessly around implementation, not survey. |

---

## 15. Open product questions

1. **Naming.** "Research Compiler" describes the function. "Paper Compiler" is shorter. "Paperdep", "Papermake", "Reprod" are other directions. Pick before public release.
2. **Should the build subagent be able to call out to web search?** Pro: catches things S2 misses. Con: blurs the boundary that local + S2 is the source of truth.
3. **Should `audit` block commits via a hook, or only warn?** Default to warn; opt-in to block.
4. **Do we ship a starter corpus** (a handful of pre-compiled famous papers) so users can try the MCP tools before running their first compile?
5. **How aggressively do we use LLMs in the compile?** LLM-based classification is expensive at scale. Heuristics-first for v1.
6. **Versioning of compiled briefs.** Should `research.md` be committed to the user's repo, or kept in `.research/`? Default: commit it. It's the build manifest.

---

## 16. Release plan

- **M0 — Skeleton (week 2):** Plugin scaffold, CLI that resolves a paper via S2 and dumps metadata. No parsing yet.
- **M1 — Parse + single-paper IR (week 4):** PDF + TeX parser producing the IR. No graph yet.
- **M2 — Citation expansion + heuristic classifier (week 7):** 1-hop expansion, heuristic edge labelling.
- **M3 — Implementation atom graph + `research.md` v0 (week 10):** End-to-end compile, ugly but real.
- **M4 — MCP server (week 12):** Query tools wired into Claude Code.
- **M5 — Skills + subagent + plugin packaging (week 14):** Full plugin installable from a marketplace.
- **M6 — Evaluation (week 16):** A/B replication study on 20 papers. Hit the success metrics or iterate.

Hard gate before M6: the plugin must compile *its own* originating paper(s) end-to-end without manual intervention.

---

## 17. References (working set)

- PaperBench (OpenAI, 2025) — replication benchmark.
- Semantic Scholar Open Data Platform (Kinney et al., 2023) — backbone.
- S2ORC (Lo et al., 2020) — IR precedent for structured scientific text.
- SciCite (Cohan et al., 2019) — starting point for citation intent classification.
- GROBID — PDF → structured XML.
- arXiv bulk access — TeX source acquisition.
- Claude Code plugin / skill / MCP / subagent documentation (Anthropic, 2025–2026).

See `02-research-context.md` for the annotated reading order.
