# Research Context — Prior Work, Reading Order, and Where We Fit

**Companion to:** `01-PRD.md`
**Purpose:** Give you (and anyone joining) a tight map of the four research areas this project sits inside, what each gets right, what each leaves on the table, and what our actual contribution is.

---

## 0. The one-paragraph framing

Four bodies of work overlap with this project: (1) scholarly knowledge graphs, (2) structured scientific text corpora, (3) citation-intent classification, and (4) paper-to-code systems. The first three are inputs we stand on. The fourth is the closest competition. Our distinct contribution is the **implementation-atom graph** — a representation that sits between citation intent and paper-to-code, and is specifically engineered to be queried by a coding agent during implementation rather than read by a human.

---

## 1. Area A — Scholarly knowledge graphs

### What exists

- **Semantic Scholar Academic Graph (S2AG).** ~200M+ papers, ~580M paper-author edges, ~2.4B citation edges. Exposed via three APIs: Academic Graph (paper/author/citation metadata, SPECTER2 embeddings), Recommendations (similar-paper suggestions), Datasets (bulk downloads). Public endpoints rate-limited around 5,000 req / 5 min shared; API keys give 1 RPS per user; batch endpoints handle up to ~500 IDs per call.
- **OpenAlex, OpenCitations.** Alternative open citation graphs. OpenAlex is broader; OpenCitations is closer to "citations as first-class objects" with stable identifiers.
- **Crossref / DataCite.** Authoritative DOI metadata; less rich than S2 for ML papers.

### What they get right

- Massive scale, stable IDs, references and citations resolved at scale.
- Semantic Scholar's "influential citation" signal is a genuinely useful heuristic — it's derived from ML analysis of citation count and surrounding citation context.
- Open-access PDF discovery via `openAccessPdf` is the cleanest available shortcut for legal full-text acquisition.

### What they leave on the table

- They are **paper-level**, not **component-level**. They will tell you "Paper A cites Paper B"; they will not tell you "Paper A's loss function is defined in equation 4 of Paper B."
- Citation context — the sentence around a citation marker — is **not** exposed by the public S2 API. (S2ORC has it, but only for the corpus snapshots, not via live API.)
- Implementation links (paper ↔ official repo) are inconsistent.

### How we use this

- S2 as the **resolver and graph accelerator** — paper ID resolution, reference/citation expansion, metadata, recommendations, open-access PDF discovery, influential-citation signal as one input to ranking.
- Not as the source of truth for any implementation claim. That comes from local parsed text.

### Key reading (priority order)

1. **Kinney et al., "The Semantic Scholar Open Data Platform" (arXiv 2301.10140).** The architectural reference; read sections 2–4.
2. **S2 API tutorial** at `semanticscholar.org/product/api/tutorial`. Read end-to-end before writing the resolver. The "How to make requests faster" section is a production checklist.
3. **OpenAlex docs.** Skim only — useful to know it exists as a fallback.

---

## 2. Area B — Structured scientific text corpora

### What exists

- **S2ORC (Lo et al., 2020).** The most directly relevant precedent. Provides structured full text for millions of open-access papers, with inline citation / figure / table mentions linked to paper objects. The JSON schema is essentially our IR target.
- **PMC OA / PubMed Central.** Biomed-focused; XML-native, very high quality, less ML coverage.
- **arXiv source tarballs (TeX).** Not "structured" in the sense above, but for ML papers TeX is often a richer source than PDF because citation keys, equations, and algorithm environments are explicit.

### What they get right

- S2ORC's schema is the right shape: paper as a tree of sections, with citations resolved to paper IDs and tagged with surrounding context.
- TeX is dramatically easier to parse correctly than PDF for ML papers when available.

### What they leave on the table

- S2ORC snapshots are static. They don't include the latest preprints.
- S2ORC doesn't classify citation roles beyond their original tags.
- TeX parsing isn't standardized — every paper has its own macros, BibTeX style, and figure layout.

### How we use this

- **Adopt the S2ORC schema as our IR shape**, with extensions for equations and algorithms as first-class objects (S2ORC has them but our extraction will be richer).
- **TeX-first when source is available** via arXiv bulk download. PDF-fallback otherwise.
- **GROBID** as the PDF → structured XML/TEI pipeline (mature, open-source, the de facto standard).

### Key reading (priority order)

1. **Lo et al., "S2ORC: The Semantic Scholar Open Research Corpus" (ACL 2020).** Read the schema sections in particular.
2. **GROBID README + the "fulltext" service documentation.** You need to know what it outputs and what it misses (math is famously a weakness).
3. **arXiv bulk data access docs** at `info.arxiv.org/help/bulk_data.html`. Specifically the source tarball format and OAI-PMH metadata harvesting.
4. **Layout-aware PDF parsers** — survey the current state once (Nougat, Marker, MinerU, GROBID + LaTeX recognition). Pick one for v1.

---

## 3. Area C — Citation intent classification

### What exists

- **SciCite (Cohan et al., 2019).** The canonical citation-intent classification dataset and model. Labels: `background`, `method`, `result_comparison`.
- **ACL-ARC / ACT2.** Earlier datasets with finer labels.
- **SciBERT / SPECTER / SPECTER2.** Pretrained encoders that perform well on citation-context classification.

### What they get right

- They validate the intuition that the **section + surrounding context** of a citation reveals its role.
- Models in this space are reasonably small and easy to fine-tune.

### What they leave on the table

- Their label sets are **too coarse for our purpose**. "Method" can mean: defines the model architecture / defines the loss / defines the dataset / defines the eval protocol / is a baseline. A coding agent needs to know which.
- They are typically trained on one-sentence citation contexts, missing the broader paragraph-level signal we need.

### How we use this

- The **idea** is exactly right: citation context determines role. We borrow it directly.
- The **label set** is ours: the eleven implementation-role labels in PRD §12.
- The **classifier** is ours: a hybrid of cheap heuristics (section type, equation proximity, repeated-citation patterns) plus an LLM call for the hard cases.

### Key reading (priority order)

1. **Cohan et al., "Structural Scaffolds for Citation Intent Classification" (NAACL 2019).** The SciCite paper.
2. **Beltagy et al., "SciBERT."** Useful pretrained encoder.
3. **One survey paper on citation function classification** (skim, don't drown).

---

## 4. Area D — Paper-to-code

### What exists

- **PaperBench (OpenAI, 2025).** 20 ICML 2024 Spotlight/Oral papers, decomposed into 8,316 gradable subtasks for replication. Best agent ~21% average score. This is our evaluation harness target.
- **Paper2Code / PaperCoder, AutoP2C, and similar systems.** Take a paper as input, attempt to produce a runnable implementation. Mostly LLM-orchestrated.
- **The broader agentic-coding literature** (Devin-likes, SWE-agent, etc.) — adjacent but not paper-focused.

### What they get right

- They name the right problem.
- They give us an evaluation methodology we can reuse.

### What they leave on the table

- They start from the target paper as the main object and effectively ignore the citation neighborhood.
- The reproducibility failures they encounter are exactly the ones our hypothesis predicts: missing details that *are* recoverable from the citation tree but are never compiled into the agent's context.

### How we use this

- **PaperBench-style evaluation** as our extrinsic metric (PRD §10.2).
- **A/B design**: baseline agent with PDF only, vs. agent with our compiled context. Same papers, same rubric.
- Read the failure modes carefully — they're our requirements list.

### Key reading (priority order)

1. **PaperBench paper / OpenAI report (2025).** Read the failure-mode analysis closely.
2. **PaperCoder / Paper2Code / AutoP2C papers.** Skim to confirm the gap.

---

## 5. Where we sit — the actual contribution

Plotting the four areas on a 2×2 of (paper-level ↔ component-level) × (read-by-human ↔ read-by-agent):

```
                       read-by-human          read-by-agent
                       ─────────────          ─────────────
paper-level    │  scholarly graphs (A)    │  paper-to-code (D)
component-level│  citation intent (C),    │  ← us
               │  S2ORC schema (B)        │
```

Nobody is squarely in the bottom-right. The contribution is:

> **A compiled, queryable, evidence-backed, component-level dependency graph of a paper's citation neighborhood, engineered to be consumed by a coding agent during implementation.**

The three things that make this different from any one of the prior areas:

1. **Implementation atoms as first-class nodes** — not just papers and citations.
2. **Implementation influence as a ranking** distinct from scholarly influence.
3. **MCP-native delivery** — the artifact is not a document, it is a queryable service that a coding agent uses while writing code.

---

## 6. Reading order if you have one week

**Day 1 — Lay of the land.**
- Skim PRD (`01-PRD.md`) and this doc.
- Read S2 Open Data Platform paper (arXiv 2301.10140), sections 2–4.
- Read S2 API tutorial end-to-end.

**Day 2 — Document IR.**
- Read S2ORC paper. Internalise the JSON schema.
- Skim GROBID docs. Run it on one paper from your target list.
- Read arXiv bulk-data access docs.

**Day 3 — Citation classification.**
- Read SciCite paper.
- Hand-label 30 citation contexts in a paper of your choice with our 11-label set. This will tell you instantly whether the label set is workable.

**Day 4 — The competition.**
- Read PaperBench report cover to cover.
- Skim one paper-to-code system (PaperCoder is a good pick).
- Write down the 3 most surprising failure modes you saw.

**Day 5 — Claude Code platform.**
- Read `03-claude-code-plugin-guide.md` (in this artifact bundle).
- Read the official Claude Code plugin / skill / MCP / subagent docs.
- Build a 1-skill toy plugin in 30 minutes to confirm the pipeline works.

**Day 6 — Pick the parser.**
- Pick one PDF parser, one TeX parser, run both on the same paper, diff the outputs. Decide which is your v1 default.

**Day 7 — Synthesis.**
- Re-read the PRD with all of the above loaded.
- Update the architecture doc (`04-architecture.md`) with any decisions that have hardened.

---

## 7. Things to not read

A trap when starting research projects like this is to over-read. Specifically:

- **Anything about LLM-based code generation in general.** Adjacent; doesn't change what we're building.
- **The full citation-graph mining literature from 2010–2018.** Most of it predates the right tools.
- **Knowledge-graph theory.** We are building one specific small graph, not a general KG.
- **Anything about agentic workflows that isn't Claude Code-specific.** Different primitives, different ergonomics.

A useful test: if the paper would not change a single line in `01-PRD.md`, you don't need to read it before M3.

---

## 8. Three "look here when you're stuck" pointers

- **When the citation classifier feels under-specified:** re-read SciCite §3 and stare at the failure cases of your heuristic v0 for 30 minutes. The label set will resolve itself.
- **When the PDF parser is the bottleneck:** switch to TeX-first for that paper, even if it complicates the pipeline. Almost every ML preprint on arXiv has TeX source.
- **When `research.md` keeps ballooning:** push more into MCP-queryable evidence and keep the brief ruthlessly short. The brief is the index, not the database.
