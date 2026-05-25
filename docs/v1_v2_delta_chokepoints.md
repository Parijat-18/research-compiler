# Open Chokepoints, Limitations & Pending Validation

**Current as of:** v2.1
**Sources:** `v1_build.md` (each stage's "Known issues"), `v2_build.md` (each section's "Chokepoint" + §14 carry-over list)
**How to read:** Each item has a severity tag — **HARD** (build fails or data corrupted without a fix), **HIGH** (significant output-quality impact), **MED** (workaround exists; annoying in practice), **LOW** (cosmetic or rare edge case). Items marked `→ v3` have a proposed fix in the roadmap at the bottom.

---

## Acquisition (Stage 2)

| ID | Sev | Issue | Workaround | Fix |
|---|---|---|---|---|
| A1 | MED | No source-quality preference — Unpaywall can serve a publisher HTML-rendered PDF for a paper that also has arXiv TeX; first-in-chain wins regardless of fidelity | Put `arxiv` first in `[sources].enabled` (already default) | Prefer TeX source over rendered PDF when both available → v3 |
| A2 | MED | `contact_email` defaults to a placeholder in `setup.sh`; Unpaywall requires a real address, S2/OpenAlex silently degrade throughput without it | Set `contact_email` in `paper-compiler.toml` | `setup.sh` should prompt on first run if placeholder detected |
| A3 | LOW | `openAccessPdf.url` sometimes redirects to an HTML landing page; bytes of HTML are accepted as a PDF (parsing then produces near-empty IR) | None; paper becomes metadata-only | Detect `Content-Type: text/html` on download and fail cleanly |
| A4 | LOW | Crossref source rarely yields full text; it's effectively metadata-only but still consumes a request slot | Remove from `[sources].enabled` if throughput matters | Promote to metadata-only source; skip in acquisition chain |

---

## Parsing (Stage 3)

| ID | Sev | Issue | Workaround | Fix |
|---|---|---|---|---|
| P1 | HIGH | TeX walker fragile on heavy macro rebinding (NeurIPS/ICML templates with custom theorem/algorithm macros); yields 2–5 sections for papers that have 20+ | Use `--refresh` after a parser fix; inspect `~/.cache/paper-compiler/parsed/<id>.v1.json` | Expand macro pre-pass; handle common conference template macro sets → v3 |
| P2 | HIGH | No diagram OCR; architecture details encoded only in figures are invisible to atoms, chunks, and retrieval | Manually `wiki-ingest` a companion paper that describes the same architecture in prose | GPT-4o-vision pass on architecture figures → v3 |
| P3 | MED | Docling (v2 default) loses algorithm boxes from TeX-originated PDFs; equations arrive as LaTeX but `\begin{algorithmic}` blocks do not | TeX path is already preferred when available (arXiv → S2 order) | Detect typeset algorithm box patterns in PDF and reconstruct |
| P4 | LOW | DOI parsing is regex-based; rare DOIs with non-standard chars (parentheses, semicolons) are misclassified | Pass arXiv id instead | Broaden DOI regex or fall through to S2 title-search |
| P5 | LOW | `_load_thebibliography` only matches literal `\bibitem{...}`; macro-wrapped bibitems silently omit references | None | Macro expansion pre-pass before thebibliography extraction |
| P6 | LOW | `confidence < 0.9` gate for ambiguous resolution is not enforced in non-interactive / forked-subagent mode | Check `resolve` JSON output manually before starting a long build | Hard-fail or emit a blocking warning below threshold in non-interactive mode |

---

## Reference Resolution & Neighborhood Expansion (Stage 4)

| ID | Sev | Issue | Workaround | Fix |
|---|---|---|---|---|
| R1 | HIGH | Reference resolution averages 45–65%; workshop papers, software releases, and technical reports (no arXiv/DOI in bib) remain unresolved — Phase 3's multi-source acquisition improved *fetching* not *resolution* | Set `SEMANTIC_SCHOLAR_API_KEY`; increase `--max-s2-requests` | Improved fuzzy BibTeX matching (venue + year hard filter in title search) → v3 |
| R2 | MED | S2 batch endpoint used only for metadata enrichment, not for the initial reference-resolution loop; ~30–50% more S2 API calls than necessary | `--max-s2-requests` cap | Batch initial resolution pass → v3 |
| R3 | MED | Depth-2 priority inheritance (`0.5 × parent_priority`) is a heuristic; papers reached through a single low-priority depth-1 path get inflated priority vs. direct depth-1 papers | Reduce `--max-depth 1` for tighter, higher-quality neighborhoods | Tune weights against a labelled evaluation set |
| R4 | LOW | Title-search resolution returns the first-best candidate even when two papers share a title; author scoring mitigates but doesn't eliminate | Use explicit arXiv/DOI ids where available | Multi-pass disambiguation with venue + year hard filter |

---

## Edge Classification (Stage 5)

| ID | Sev | Issue | Workaround | Fix |
|---|---|---|---|---|
| E1 | HIGH | Confidently-wrong heuristics never trigger LLM rescue — the threshold gates on heuristic confidence, not correctness; a heuristic that is high-confidence and wrong is never corrected | Raise `--classifier-llm-calls` to widen LLM coverage | Sample a random 10% of high-confidence heuristic edges for LLM verification → v3 |
| E2 | MED | `intent` field (`supports / refutes / extends / uses / discusses`) from Phase 4 is stored on edges in DB but not surfaced by any MCP tool; invisible to skills | `graph_sql("SELECT intent FROM edges WHERE ...")` | Add `intent` to `citation_neighbors` response |
| E3 | LOW | Multi-label `edge_roles` table is populated but all downstream tools read only `best_role` | `graph_sql` on `edge_roles` for multi-label use | Expose `top_roles(n=3)` in `citation_neighbors` |

---

## Atom Extraction (Stage 6)

| ID | Sev | Issue | Workaround | Fix |
|---|---|---|---|---|
| AT1 | HIGH | LLM extraction quality is bimodal: clean method paragraphs → good atoms; short / notation-heavy paragraphs → 0–1 atoms with full LLM cost | `--no-llm` for smoke tests; `--atom-llm-calls` cap to control spend | Pre-filter paragraphs below a complexity threshold before LLM pass → v3 |
| AT2 | MED | Phase 5 budget allocator hits `--atom-llm-calls` cap (default 80) on neighborhoods > 80 parsed papers; tail papers fall back to heuristic-only extraction | Raise cap or reduce `--max-papers` | Adaptive cap scaled to neighborhood size |
| AT3 | MED | `subcategory` field (LLM-emitted refinement, e.g. `objective:contrastive`) is not used by any retrieval path; only surfaces in community summarizer and audit sub-skill prompts | `graph_sql("SELECT subcategory FROM atoms WHERE ...")` | Index `subcategory` in atoms_fts; expose as optional filter in `find_atom` |
| AT4 | LOW | `_is_junk_name` rejects by length/word-count/letter ratio but not by noun-phrase structure; multi-word hyperparameter names occasionally slip through | Accepted; downstream impact minimal | Lightweight NP detector post-filter |
| AT5 | LOW | `dependencies` between atoms is rarely populated by the extractor; implementation topological order mostly reduces to category order | None | Detect cross-atom references in method paragraphs during extraction (see S2) |

---

## Scoring & Ranking (Stage 7)

| ID | Sev | Issue | Workaround | Fix |
|---|---|---|---|---|
| S1 | LOW | Score weights (0.7 implementation_influence / 0.3 scholarly_influence) are untuned placeholders from v0.1 | None | Calibrate against a labelled evaluation set (see V1 in Validation section) |
| S2 | LOW | `dependencies` between atoms is rarely populated; topological implementation order reduces to category order rather than true dependency order | None | See AT5 |
| S3 | LOW | Recency is under-weighted for recent preprints whose citation count hasn't caught up yet; implementation_influence dominance partially compensates | None | Cap scholarly decay window at 3 years for preprints |

---

## DB / Retrieval

| ID | Sev | Issue | Workaround | Fix |
|---|---|---|---|---|
| D1 | MED | `graph_sql` SELECT/WITH enforcement uses string prefix matching; a crafted comment block could bypass it (acceptable for local read-only; not network-safe) | Local-only deployment (current use case) | Proper SQL AST parser for safety-critical deployments |
| D2 | MED | `paragraph_ids` filter in `paper_text` accepts ids without validating they belong to the requested `paper_id`; mismatches silently return empty | Cross-check via `graph_sql` | FK validation in `paper_text` handler |
| D3 | MED | `paper_text(full=True)` byte budget is unenforced; a long paper can return ~30 KB in one call | Use snippet-first default; only pass `full=True` on targeted lookups | Hard token cap with truncation notice |
| D4 | LOW | `chunk_kind` classification is regex/heuristic over text + section_type; dense math paragraphs occasionally mislabelled as `equation_block` | Inspect with `graph_sql("SELECT chunk_kind, text FROM chunks WHERE ...")` | Train lightweight classifier on labelled chunk text patterns |
| D5 | LOW | `query_chunks` doesn't auto-infer a `kinds` preference from query semantics; user must pass `kinds=["table"]` explicitly for ablation queries | Pass `kinds` explicitly | Router should infer kind from query phrasing (e.g. "ablation table" → `kinds=["table"]`) |
| D6 | LOW | `route_query` regex rules tuned on JEPA audit corpus; comparative/thematic queries on non-ML corpora may get wrong `local/global` routing | Override with `mode=` parameter | Test and recalibrate on physic-simulo build (see V7 in Validation) |
| D7 | LOW | Reranker is BM25 + cosine + quality prior + community boost — all hand-tuned, none learned | None | Fine-tune on labelled query-chunk pairs from compiled corpora → v3 |

---

## Chunking

| ID | Sev | Issue | Workaround | Fix |
|---|---|---|---|---|
| C1 | MED | Quality floors per `chunk_kind` (table=0.55, caption=0.45, equation_block=0.50, etc.) are guesses; not calibrated against retrieval feedback | Adjust thresholds in `text_utils.py` manually | Calibrate on annotated relevance judgments |
| C2 | LOW | 200-char overlap is fixed; dense related-work sections over-produce overlapping chunks, short paragraphs never overlap | None | Adaptive overlap proportional to paragraph length → v3 |
| C3 | HIGH | **Overlap is character-tail, not sentence-boundary-aware.** `split_with_overlap` carries overlap by slicing `out[-1][-overlap_chars:]` — a raw 200-char suffix that starts mid-sentence or mid-word. Every non-first chunk in a split paragraph begins with a dangling fragment: embedding the truncated prefix lowers similarity with clean queries; retrieved text displays mid-sentence. Root cause: `text_utils.py:191`. | None — there is no workaround; the truncation is baked in | Replace character-tail carry with a sentence-boundary carry: after emitting a chunk, re-walk the last `N` complete sentences (where `N` keeps total overlap ≤ 200 chars) and use those as the prefix for the next chunk → v3 |
| C4 | HIGH | **Sentence splitter misses scientific text terminators.** `split_with_overlap` uses `(?<=[.!?])\s+` to detect sentence boundaries (`text_utils.py:183`). Research paper text ends sentences with `:` (theorem names, algorithm step labels), `;` (enumerated proof steps), `∎` or `□` (end-of-proof markers), and bare newlines after display equations. These are never split points — a 3-paragraph proof of a theorem becomes one unsplit 2,000-char window that gets truncated at the character budget, severing the conclusion. | None | Extend the sentence-split regex to include `: `, `; `, `\n\n`, and `[∎□]` as sentence-terminal markers; or use `nltk.sent_tokenize` with a custom abbreviation list for scientific notation |
| C5 | HIGH | **No token-budget check against the embedding model's max context.** `CHUNK_CHAR_BUDGET = 1800` and `split_with_overlap(target_chars=750)` use character counts as a proxy for tokens (`graph_db.py:62`, `text_utils.py:174`). `bge-small-en-v1.5` has a **512-token hard limit**. A LaTeX-heavy paragraph at 750 chars can easily exceed 400–500 tokens (LaTeX math tokenizes at ~3–5 chars/token vs ~4–5 chars/token for prose). Chunks that exceed 512 tokens are silently truncated by the SentenceTransformer encoder — the tail of the chunk contributes nothing to the embedding. `tiktoken` is already a declared dependency and could be used for an accurate estimate. | Reduce `target_chars` to ~500 (conservative floor for LaTeX-dense text) | Replace `target_chars` character budget with a `max_tokens` budget computed via `tiktoken`; default to 400 tokens (headroom below the 512-token encoder limit) → v3 |
| C6 | MED | **Short paragraphs produce isolated micro-chunks.** A paragraph of 1–2 sentences (common for equation labels, transitional sentences, step headings in algorithm descriptions) is stored as its own chunk with no neighboring context. bge-small embeddings of 20–50 word chunks are noisy and nearly indistinguishable for semantically similar short sentences. The atom extractor then finds no evidence span for implementation atoms defined in the surrounding paragraphs because the relevant context was split away. | None | Merge consecutive short paragraphs (< 100 chars or < 20 tokens) with the next paragraph before chunking; emit as a single chunk unless the merged size exceeds the token budget → v3 |
| C7 | MED | **No logical-unit boundary awareness for theorems, proofs, and algorithms.** The chunker operates at the paragraph level (IR paragraphs from `parse/pdf.py` or `parse/tex.py`). A theorem statement and its proof span multiple IR paragraphs but are a single logical unit for retrieval — a query about "how is theorem X proved" should retrieve both. Currently the theorem statement is chunk N and the proof is chunks N+1 … N+k, each embedded independently. The atom extractor assigns evidence to exactly one chunk. | None | Detect theorem/proof/algorithm structural pairs from `section_type` and IR paragraph metadata; merge into a single logical chunk before splitting, then split only if the merged unit exceeds the token budget → v3 |
| C8 | LOW | **Overlap dedup logic is effectively dead code.** `split_with_overlap:205` deduplicates with `chunk.startswith(deduped[-1][-overlap_chars:]) and chunk in deduped[-1]`. The second condition (`chunk in deduped[-1]`) is only true if the entire new chunk is a substring of the previous — which almost never happens for any non-trivial overlap. The dedup check does not fire in practice, meaning genuine duplicate overlap windows from back-to-back short sentences are not removed. | None | Fix: remove the `and chunk in deduped[-1]` condition; dedup solely on startswith check |

---

## Communities (Stage 9)

| ID | Sev | Issue | Workaround | Fix |
|---|---|---|---|---|
| CM1 | MED | Community recompute is wholesale on every compile and every `wiki-ingest`; acceptable for ≤ 500 papers, slow and redundant for larger or frequently-ingested corpora | Acceptable at current scale | Incremental Louvain update on ingest → v3 |
| CM2 | LOW | Louvain resolution = 1.4 is a magic number verified only on the JEPA corpus; other corpora may need different values | Edit `communities.py:121` directly | Expose as `[communities] resolution` config key |
| CM3 | LOW | Community LLM summarization budget (~12 calls) is separate from `--classifier-llm-calls` and `--atom-llm-calls`; easy to overlook when estimating total compile cost | Track separately in build-manifest.json | Unify all LLM call budgets under a single `--max-llm-calls` cap |

---

## Wiki & Memory Plane

| ID | Sev | Issue | Workaround | Fix |
|---|---|---|---|---|
| W1 | MED | `decisions.md` content not re-embedded into `chunks_fts` until the next full compile; a decision rationale is unsearchable by `query_chunks` between compiles | `Read decisions.md` directly (not blocked by PreToolUse hook) | Re-embed on each `record_decision` write → v3 |
| W2 | MED | `record_decision` call rate is unbounded; the "don't log routine work" instruction in `CLAUDE.md` is fuzzy; over-recording drowns the log | User discipline | Add explicit `kind` enum (`ambiguity / default-adopted / tried-and-failed`) and reject calls that don't fit |
| W3 | MED | Memory plane has no GC: `decisions.md` grows forever; `sessions/` accumulates one file per session; at ~5 sessions/week, manual triage required within a year | Manual archive | Auto-archive sessions older than N weeks; compact `decisions.md` entries with same slug → v3 |
| W4 | MED | Wiki articles regenerated wholesale on every compile; hand-edits to generated atom/paper/community articles are lost; only `wiki/answers/` survives | Only edit files under `wiki/answers/` | Frontmatter-driven merge: preserve user-added sections across regeneration |
| W5 | LOW | `wiki-lint` is structural only (broken wikilinks, orphan atoms, stale paper refs); semantic contradictions between papers and between decisions are undetected | Periodic manual review | LLM contradiction detection pass over `answers/` + `decisions.md` → v3 |
| W6 | LOW | Promotion threshold (≥ 2 atoms in ≥ 2 communities) is heuristic; a valid synthesis touching only 1 community is never auto-promoted | Manually write `wiki/answers/<slug>.md` | User-triggered `promote this answer` command |
| W7 | LOW | `CLAUDE-PAPER-CONTEXT.md` regenerated on every compile; user annotations in that file are lost | None; edit `decisions.md` instead (survived across compiles) | Merge annotated sections like wiki article fix (W4) |

---

## MCP Server

| ID | Sev | Issue | Workaround | Fix |
|---|---|---|---|---|
| M1 | MED | No rate limit on `record_decision` / `append_session_note` after the user clicks through the `ask` gate; Claude can call them rapidly in a loop | Rely on user reviewing each confirmation | Per-session write budget or cooldown between writes |
| M2 | LOW | Cold-start ~1.5 s for bge-small embedder load on first call (held in module state after) | Acceptable; first-call delay only | Pre-warm embedder on session start via `get_paper_context` call in SessionStart hook |
| M3 | LOW | `citation_neighbors` returns `role` and `confidence` but not `intent`; the Phase 4 intent field (supports/refutes/extends/uses/discusses) is recorded in the DB but invisible to skills | `graph_sql("SELECT intent FROM edges WHERE from_paper_id=...")` | Add `intent` to `citation_neighbors` response (see E2) |

---

## Skills & Hook Scripts

| ID | Sev | Issue | Workaround | Fix |
|---|---|---|---|---|
| SK1 | MED | `detect-intent.sh` is a bash grep; nuanced or phrasing-ambiguous prompts route incorrectly (e.g. "implement the procedure" can match `implement-procedure` or `port`) | Override the suggestion; invoke the right sub-skill manually | Semantic intent detection via a 20-token LLM call or small classifier → v3 |
| SK2 | MED | `allowed-tools` whitelist is per-SKILL.md; adding a new MCP tool requires editing ~10 SKILL files | Edit all affected files | Declarative whitelist at the parent skill level with per-sub-skill override exceptions |
| SK3 | LOW | `implement-X` and `audit-X` sub-skills share ~30% of MCP call sequences; duplicated across 14 files | None | Shared `query-atom-evidence.md` snippet included by both families |
| SK4 | LOW | 10 hook scripts are exit-code-meaningful (exit 2 blocks tool calls); each new script is a new attack surface; Bash 3.2 compatibility required | Test with `bash --posix` on any new script | CI lint step checking Bash 3.2 compat + exit-code contract |

---

## CLI & Infrastructure

| ID | Sev | Issue | Workaround | Fix |
|---|---|---|---|---|
| I1 | MED | `paper-compiler cache prune` is a stub; cache grows monotonically (~50–200 MB per compiled paper; multi-paper setups hit GB scale) | Manual `rm -rf ~/.cache/paper-compiler/papers/<id>` | Implement `cache prune --older-than N` → v3 |
| I2 | LOW | Only one S2 API key supported; concurrent or multi-user compiles share one rate-limited slot | Stagger compiles | Round-robin key pool in `s2_client.py` |
| I3 | LOW | `--max-budget-usd` not passed per LLM call via `claude -p`; no per-compile spend guardrail | `--classifier-llm-calls` + `--atom-llm-calls` caps as proxy | Wire cumulative token tracking to a hard budget stop |

---

## Build Gate Discrepancy

| ID | Sev | Issue |
|---|---|---|
| BG1 | MED | `validate-build-manifest.sh` gates (from `v2_build.md §10` and root `CLAUDE.md`) are `coverage_pct ≥ 50`, `atoms_extracted ≥ 8`. The `build-research-context` SKILL.md lists `coverage_pct ≥ 70`, `atoms_extracted ≥ 30` as v2.0 acceptance invariants. The JEPA build (165 atoms, ~60% coverage) would pass the script gates but fail the SKILL.md gates. One source is wrong. |

Likely resolution: the SKILL.md numbers are aspirational targets for a full v2.0 multi-source build; the script gates are the hard-fail floor. These should be clearly separated — script gates as hard-fail thresholds, SKILL.md numbers as soft quality targets with explicit labels.

---

## Validation Still Pending

Claims in the PRD, hypothesis, or documentation that have never been empirically verified against a real build.

| ID | Area | Claim / Open question | What verifies it |
|---|---|---|---|
| V1 | Hypothesis | Condition C (full MCP Graph RAG) beats Condition A (paper PDF only) by ≥ +10 pp on PaperBench-style replication scoring | Run the 3-condition study from `docs/05-evaluation-plan.md` on ≥ 3 papers across ≥ 2 domains |
| V2 | Hypothesis | Brief alone (Condition B) carries most of the benefit; full MCP closes the last 3–5 pp gap | Same study, include Condition B |
| V3 | Hypothesis | Hallucination rate cut in half under Condition C | Measure invented atom names / method details vs. verifiable against evidence spans |
| V4 | Domain neutrality | Plugin described as domain-neutral (ML, physics, chemistry, biology, economics, climate) but built and tested only on ML papers | Run a physics compile (e.g. `arxiv:2602.00658` physic-simulo target) and verify atom categories, routing, and retrieval quality |
| V5 | Edge accuracy | Phase 4 edge accuracy claimed ~78% per role; dev sample was 100 edges from JEPA corpus only | Test on a different corpus; ideally a domain-distinct paper (physics, biology) |
| V6 | Community routing | Community boost lifts MRR by ~12% vs no-boost; measured on a 20-query dev set from JEPA | Re-run on a second compiled corpus with independently labelled relevance judgments |
| V7 | Query router | `route_query` rules work correctly for comparative/thematic queries; only tested on JEPA | Build physic-simulo corpus; run router against domain-specific queries; measure misrouting rate |
| V8 | Docling vs Marker | Docling claimed ~10× faster parse; no head-to-head comparison of atom quality or evidence completeness | Compare atom count, evidence quality, and coverage on 5 papers compiled with both backends |
| V9 | Cross-session continuity | `resume-session` + `decisions.md` claimed to prevent re-deriving atoms across sessions | 3-session implementation task; measure what fraction of atoms are re-queried vs. retrieved from prior session notes |
| V10 | Build gate thresholds | Gate values in `validate-build-manifest.sh` and `build-research-context` SKILL.md disagree (see BG1 above) | Audit the script; pick canonical values; update both sources |

---

## External Dependencies & APIs

Chokepoints that originate in third-party libraries or hosted services — not internal pipeline logic. Severity here means impact on a typical 200-paper compile.

---

### Semantic Scholar API

| ID | Sev | Issue | Workaround | Fix |
|---|---|---|---|---|
| X1 | HIGH | `/graph/v1/paper/{id}/references` is hard-capped at 1,000 items even with `limit=1000`. Papers with dense bibliographies (survey papers, reviews) silently drop references beyond the cap — neighborhood expansion misses papers that appear only in those tail refs. | `--max-depth 1` narrows scope; not a real fix | Use the citations endpoint in reverse (inbound neighbors from cited papers) to recover missing edges → v3 |
| X2 | HIGH | Without `SEMANTIC_SCHOLAR_API_KEY`, rate limit is effectively 1 RPS unauthenticated (token bucket already enforces `s2.rate_limit_rps = 1.0`). A 200-paper build makes ~400–600 S2 requests → 7–10 min of pure API wait, back-to-back. With a key (~10 RPS), same build is ~1 min. | Set `SEMANTIC_SCHOLAR_API_KEY` — high-value, free API key from semanticscholar.org | Document in setup.sh as a blocking prerequisite, not optional hint |
| X3 | MED | S2 `openAccessPdf.url` field goes stale: PDFs move or paywalls change after S2 crawled. A URL returns a 200 but serves publisher HTML (already A3 for Unpaywall; same failure mode here). S2 source (`sources/s2.py`) downloads the S2 OA PDF without Content-Type checking. | None at source level | Detect `Content-Type: text/html` on PDF download; mark paper as metadata-only and continue |
| X4 | MED | S2 has poor coverage of preprints < 6 months old: `citationCount` and `influentialCitationCount` are often 0, making the Phase 7 `scholarly_influence` score zero. Recent target papers and their recent neighborhood get under-ranked. | None | Cap scholarly decay window at 3 years for papers with year ≥ current−1 (see S3, which is the same issue for recency) |
| X5 | MED | Batch endpoint (`/graph/v1/paper/batch`) is used only for metadata enrichment, not the initial resolution loop (already R2). But more specifically: the batch endpoint silently returns `null` for unknown IDs instead of an error — if a resolution produces a bad ID, the batch call masks it rather than raising. | `graph_sql("SELECT paper_id FROM papers WHERE title IS NULL")` to detect | Validate non-null returns from batch against the input id list |
| X6 | LOW | S2 search (`/graph/v1/paper/search`) returns the first-best match even when multiple papers share a near-identical title. Author-overlap scoring in `resolve.py` mitigates but doesn't eliminate false positives (same as R4 but specific to the S2 search endpoint behavior). | Pass DOI/arXiv id directly when available | Multi-field scorer: require year ± 1 and ≥1 overlapping author surname |
| X7 | LOW | S2 `fieldsOfStudy` is a coarse taxonomy (e.g. `["Physics"]`, `["Computer Science"]`) with no sub-field granularity. The pipeline doesn't use it today, but it would be the natural hook for routing domain-specific chunking or community summarization prompts. | None | Expose `fieldsOfStudy` on atoms/papers for domain-aware prompt selection → v3 |

---

### Docling (PDF parser)

| ID | Sev | Issue | Workaround | Fix |
|---|---|---|---|---|
| X8 | HIGH | Docling invokes **RapidOCR** for every page that lacks a native text layer. For a 200-paper neighborhood with even 15–20% scanned PDFs, this creates a long serial OCR loop: each paper's Docling converter initializes RapidOCR fresh per document (no persistent process), adding 2–5 s overhead per paper before OCR starts. Build times of 30–60 min are typical (observed on the physic-simulo build). | None — OCR is invisible inside Docling. Skipping PDFs by setting `max_papers` lower helps. | Pre-screen PDFs with `pdfminer` text extraction; pass Docling a `no_ocr=True` flag (available in newer Docling) for text-layer PDFs, reserve OCR for scanned ones. |
| X9 | MED | Docling `DoclingDocument` API changes across minor versions — `item.text` vs `item.orig`, `iterate_items()` yielding `(item, level)` vs just `item`. The compatibility shims in `parse/pdf.py:79–99` already paper over two variants but will break silently on a third. | Pin `docling>=2.0,<3` | Add a version sniff at import and fail loud if the API shape is unrecognized |
| X10 | MED | Docling has no GPU acceleration for RapidOCR on Apple Silicon (MPS). OCR runs on CPU regardless of available hardware. On M-series Macs, this is 5–10× slower than a CUDA-equipped Linux box. | None | Investigate `rapidocr-paddle` backend (supports Apple Neural Engine) as Docling OCR backend override |
| X11 | LOW | Docling can spike to 1–2 GB RAM while processing a large PDF with many embedded figures (the figure decoder holds bitmaps in memory). On builds with 400 papers, peak RAM is unbounded across the serial parse loop. | None; tolerable on machines with ≥16 GB | Stream-process pages; limit Docling to text-only extraction when `parse.no_figures = true` config flag is set → v3 |
| X12 | LOW | **Alternative if OCR speed becomes a hard blocker:** GROBID (academic PDF parser from INRIA) has better citation/section structure extraction than Docling and runs as a persistent Java server (no per-document init cost). Nougat (Meta) is fine-tuned on arXiv PDFs specifically. Neither requires OCR for text-layer PDFs. Both are significantly more complex to deploy than `pip install docling`. | None currently | Evaluate GROBID for the non-OCR PDF subset; keep Docling as OCR fallback → v3 |

---

### arXiv e-print API

| ID | Sev | Issue | Workaround | Fix |
|---|---|---|---|---|
| X13 | MED | arXiv has no published rate limit for the e-print endpoint (`/e-print/<id>`) but imposes IP-based throttling around 3 req/sec. The `arxiv` source uses the shared `sources.rate_limit_rps = 2.0` bucket, which is correct — but it shares that bucket with OpenAlex and Unpaywall. If all three fire in parallel for the same paper, the shared bucket still allows 2 RPS per source simultaneously. | None (the shared bucket in `_http.py` is per-source, not global across sources) | Create a single global HTTP bucket shared across all sources, not one per source |
| X14 | MED | arXiv API v1 (used here: `https://arxiv.org/e-print/`) is the legacy endpoint. The arXiv REST API v2 (`https://api.arxiv.org/`) is the current standard and supports metadata + link resolution. The e-print endpoint itself won't be deprecated soon, but the API metadata path should eventually migrate. | No action needed now | Note in `sources/arxiv.py` as a future migration target |
| X15 | LOW | ~3% of arXiv papers serve a PDF from the e-print endpoint instead of a TeX tarball (handled in `arxiv.py:72`). But some papers also serve a malformed or single-file `.tex` tarball that fails `_load_thebibliography` (already P5). The `arxiv_tex` success path gives no quality signal — a malformed tarball looks identical to a good one until parsing. | Inspect `~/.cache/paper-compiler/parsed/<id>.v1.json` | Emit a warning when `len(sections) < 3` for an arxiv_tex parse result |

---

### OpenAlex

| ID | Sev | Issue | Workaround | Fix |
|---|---|---|---|---|
| X16 | MED | `best_oa_location.pdf_url` is populated for only ~40% of OpenAlex works. The remaining 60% have a `url` that points to a landing page, not a PDF. The code already handles the `.pdf` extension heuristic (line 66–68 in `openalex.py`) but misses cases where PDFs are served from non-obvious URLs (institutional repositories, PubMed Central). | None | Add `Content-Type` probing on `url` before marking as no-hit |
| X17 | LOW | OpenAlex resolves old-format arXiv IDs (e.g. `astro-ph/0601001`) via the `10.48550/arXiv.astro-ph/0601001` DOI proxy but this often fails because the slash confuses some resolvers. Physics papers from pre-2007 are frequently missed. | Pass the DOI directly if available | URL-encode the arXiv ID component in the DOI proxy path |
| X18 | LOW | OpenAlex imposes a "polite pool" requirement (email via `mailto=` param). Without it, requests are served from a shared lower-throughput pool with no documented rate limit — in practice ~5 req/sec, but can drop lower under load. The `contact_email` requirement is shared with Unpaywall and Crossref but isn't validated at startup — it silently degrades throughput. | Set `contact_email` in config | Same as A2: prompt on first run if placeholder or unset |

---

### Unpaywall

| ID | Sev | Issue | Workaround | Fix |
|---|---|---|---|---|
| X19 | MED | Unpaywall is **DOI-only** — no arXiv ID or title-based lookup. Papers that lack a DOI (unpublished preprints, workshop papers, technical reports) are completely skipped even if they have open-access PDFs. Since workshop papers and preprints are already R1's resolution gap, Unpaywall doesn't help where it's most needed. | Source order puts arXiv first, which covers the arXiv-preprint case | None; this is a fundamental Unpaywall limitation. Document explicitly. |
| X20 | LOW | Unpaywall has no batch endpoint — every DOI is a separate HTTP request. For a 200-paper compile where 50% have DOIs, that's ~100 sequential Unpaywall requests at 2 RPS = 50 sec of wall time. OpenAlex covers the same papers with a single-lookup path and has better coverage. | Put `openalex` before `unpaywall` in `sources.enabled` | Demote Unpaywall to last resort after OpenAlex |

---

### bge-small-en-v1.5 (embedding model)

| ID | Sev | Issue | Workaround | Fix |
|---|---|---|---|---|
| X21 | HIGH | `bge-small-en-v1.5` is English-only. Papers in the citation neighborhood from non-English venues (or papers with non-English abstracts) get poor embeddings — cosine similarity scores are unreliable, degrading vector retrieval for those papers. Physics and chemistry corpora have higher non-English representation than ML. | None | Switch to `multilingual-e5-small` for non-ML corpora, or `specter2` (scientific fine-tuned, English but domain-aware) |
| X22 | MED | 384 dimensions is the smallest bge variant. It's fast but misses fine-grained semantic distinctions between similar physics/math concepts (e.g. "Riemann solver" vs "Godunov scheme" both map near "numerical scheme"). FTS5 lexical search partly compensates, but hybrid ranking still degrades on highly technical vocabulary. | None | Configurable model: `bge-base-en-v1.5` (768-dim) or `specter2` (scientific BERT) behind `[retrieval] embedding_model` config key |
| X23 | MED | `sentence-transformers` model version is not pinned in `pyproject.toml` (`sentence-transformers>=2.7`). A future `sentence-transformers` release that bumps `bge-small` weights would change all embeddings silently, making the `chunks_vec` table in an existing `research.db` incompatible with queries from a newer build. | Pin `sentence-transformers` version or add an embedding model hash to `build-manifest.json` | Store embedding model name + version in `papers` table metadata; warn on version mismatch at MCP server startup |
| X24 | LOW | First-call cold start is ~1.5 s (already M2). But the model is downloaded from HuggingFace Hub on first use (~90 MB for bge-small). This download happens silently mid-build with no progress indicator. On a slow connection it can stall the build for minutes. | Pre-download: `python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-en-v1.5')"` | Add an explicit `paper-compiler prefetch` command that downloads all model weights before starting a build |

---

### sqlite-vec

| ID | Sev | Issue | Workaround | Fix |
|---|---|---|---|---|
| X25 | HIGH | `enable_load_extension(True)` is required to load sqlite-vec but is **disabled** in some Python builds (notably the system Python on macOS and some conda environments). When it fails, `_try_load_vec` silently returns `False` and the entire vector retrieval path is skipped — `query_chunks` falls back to FTS5-only with no warning to the user. | Use a venv Python or homebrew Python | Emit a visible warning at MCP server startup if vec is not loaded; document in setup.sh |
| X26 | MED | The `vec0` virtual table is **append-only during the build**. There is no `UPDATE` or `DELETE` path — a re-embed after a parser fix requires dropping and recreating the entire `chunks_vec` table. For a 400-paper corpus, this means re-embedding all ~10,000 chunks on every `--refresh` run even if only 10 chunks changed. | `--refresh` already invalidates the whole DB; re-embedding is unavoidable today | Incremental embed: hash each chunk text; only re-embed chunks whose hash changed → v3 |
| X27 | LOW | sqlite-vec uses linear scan for cosine similarity (`knn=` parameter). For 10,000+ chunk vectors at 384 dimensions, each query is ~50 ms (acceptable). At 50,000+ vectors (multi-paper compiles), latency will degrade noticeably. There is no HNSW or IVF index. | Acceptable at current scale (single paper, 200-paper neighborhood) | For multi-paper corpus (v3 roadmap item 6), consider switching the vector store to hnswlib or faiss |

---

### NetworkX + Louvain

| ID | Sev | Issue | Workaround | Fix |
|---|---|---|---|---|
| X28 | MED | `networkx.algorithms.community.louvain_communities` is pure Python. For 400-paper neighborhoods with atom co-occurrence edges (O(n²) paper-pair loop in `communities.py:65–79`), the graph build + Louvain detection takes 3–10 s. For 1,000+ papers (multi-paper compile) this will be a bottleneck. | Acceptable at current scale | Switch to `python-igraph` + `leidenalg` for 5–20× speedup and better community quality (Leiden algorithm has no resolution limit problem unlike Louvain) → v3 |
| X29 | LOW | Louvain in NetworkX has a known **resolution limit**: communities smaller than `√(2m)` edges (where `m` is total edges) may be merged into larger ones regardless of the `resolution` parameter. For sparse citation graphs (many papers with few edges), small legitimate topic clusters get swallowed. | Raise `resolution` above 1.4 in `communities.py:121` | Expose as `[communities] resolution` config key (already CM2); document resolution-limit behavior |
| X30 | LOW | If `louvain_communities` raises (e.g. isolated node, empty graph edge cases), `communities.py:91–98` falls back to `greedy_modularity_communities`. Greedy modularity is slower (O(n³) worst case) and produces lower-quality communities on sparse graphs. The fallback has no log message distinguishing it from a normal Louvain run. | None | Log "WARN: fell back to greedy modularity" at the compile stage |

---

### rank-bm25 + FTS5 (lexical retrieval)

| ID | Sev | Issue | Workaround | Fix |
|---|---|---|---|---|
| X31 | MED | FTS5's built-in stemmer (Porter algorithm, English-only) doesn't handle scientific terminology. "Transcritical" ≠ "transcrit", "Godunov" has no stem match, "Navier–Stokes" is tokenized as two terms. Queries on non-ML corpora (physics, chemistry) suffer higher miss rates. | Add domain-specific synonym expansion as a pre-query step | Configure FTS5 with a custom tokenizer or pre-expand technical terms via a small lookup table → v3 |
| X32 | LOW | `rank-bm25` (used for in-memory BM25 reranking on top of FTS5 results) is pure Python. For a 200-candidate rerank pass it's negligible, but the index is rebuilt from scratch on every `query_chunks` call — there's no persistent BM25 index. | Acceptable at current call frequency | Cache the BM25 index in MCP server module state after first build |

---

### bibtexparser + pylatexenc

| ID | Sev | Issue | Workaround | Fix |
|---|---|---|---|---|
| X33 | MED | `bibtexparser` v1.4 (current dependency) is the legacy API. v2.0 has a breaking interface change and better malformed-BibTeX handling. Conference proceedings BibTeX (especially AAAI, IJCAI, ACM) frequently have non-standard fields, unescaped special chars, or duplicate keys that cause v1.4 to silently drop entries or raise. | Inspect `~/.cache/paper-compiler/parsed/<id>.v1.json` for missing references | Migrate to `bibtexparser>=2.0` — breaking but well-documented migration guide exists |
| X34 | LOW | `pylatexenc` macro expansion is limited to the macros in its built-in dictionary. NeurIPS/ICML template-specific macros (`\iclraddress`, `\citet`, `\citep` with custom options, algorithm formatting macros) are not expanded — text extraction produces LaTeX fragments instead of clean text (already P1, but root cause is pylatexenc). | Use `\text{...}` in equations where possible | Add a pre-pass that expands common conference template macros before handing to pylatexenc |

---

### tenacity (retry behaviour)

| ID | Sev | Issue | Workaround | Fix |
|---|---|---|---|---|
| X35 | LOW | S2 client uses `stop_after_attempt(5)` with `wait_exponential_jitter(initial=1, max=20)`. If S2 is fully down, this means up to ~60 s of retry accumulation per request before raising. A 200-paper build that hits a S2 outage can block for 60 s × 400 requests = hours before eventually failing. There is no circuit-breaker pattern. | Use `--max-s2-requests` to limit requests; kill the build if S2 looks down | Add circuit-breaker: after 3 consecutive 5xx failures, abort the build with a clear "S2 appears down" message |

---

## v3 Roadmap (ordered by estimated impact)

| Priority | Item | Chokepoints addressed |
|---|---|---|
| 1 | Source-quality preference in `acquire.py` — prefer TeX over publisher PDF | A1 |
| 2 | **Docling OCR pre-screen** — detect text-layer PDFs with `pdfminer` before invoking Docling; pass `no_ocr=True` for text-layer papers, reserve OCR path for genuinely scanned PDFs. Eliminates the 30–60 min OCR stall on physics/chemistry builds. | X8, X10 |
| 3 | **Enforce `SEMANTIC_SCHOLAR_API_KEY` as a hard build prerequisite** in `setup.sh` and `build-research-context` SKILL.md — unauthenticated builds are 10× slower (7–10 min API wait vs ~1 min). Emit a blocking error, not a hint. | X2 |
| 4 | **Token-budget chunking** — replace `target_chars=750` / `CHUNK_CHAR_BUDGET=1800` with a `max_tokens=400` budget via `tiktoken`; prevents silent encoder truncation of LaTeX-heavy paragraphs that exceed bge-small's 512-token limit | C5 |
| 5 | **Sentence-boundary-aware overlap** — replace the character-tail carry in `split_with_overlap` (`text_utils.py:191`) with a complete-sentence carry; eliminates mid-word/mid-sentence chunk prefixes that degrade embedding quality and retrieved text readability | C3 |
| 6 | **Extended sentence terminators for scientific text** — add `:`, `;`, `\n\n`, `∎`, `□` to the sentence-split regex (`text_utils.py:183`); prevents theorem/proof/algorithm text from merging into one unsplit 2,000-char window | C4 |
| 7 | Re-embed `decisions.md` entries into `chunks_fts` on write | W1 |
| 8 | **Emit visible warning at MCP startup when sqlite-vec fails to load** (currently silent fallback to FTS5-only) | X25 |
| 9 | **Global HTTP rate bucket across all acquisition sources** — per-source buckets allow simultaneous arXiv + OpenAlex requests, risking IP throttling | X13 |
| 10 | Delta community detection — skip wholesale recompute on small ingests | CM1 |
| 11 | **Short-paragraph merging** — merge consecutive paragraphs < 100 chars before chunking to eliminate isolated micro-chunks with noisy embeddings | C6 |
| 12 | **Logical-unit chunking for theorems + proofs** — detect theorem/proof/algorithm pairs from section metadata; merge into one unit before splitting so retrieval captures the full argument | C7 |
| 13 | **Configurable embedding model** — add `[retrieval] embedding_model` config key; document `specter2` as recommended swap for non-ML corpora | X21, X22 |
| 14 | **Pin embedding model version in `build-manifest.json`** — warn at MCP server startup on version mismatch with `chunks_vec` | X23 |
| 15 | Multi-paper compile — shared corpus across N targets (PaperBench-ready) | V1, V2 |
| 16 | **Content-Type gating on PDF downloads** — detect `text/html` from S2/OpenAlex/Unpaywall and mark paper metadata-only instead of caching HTML as a PDF | X3, A3 |
| 17 | Learned reranker — fine-tune on labelled query-chunk pairs | D7 |
| 18 | **S2 references >1,000 workaround** — supplement `/references` (capped at 1,000) with reverse `/citations` lookup for survey papers | X1 |
| 19 | Semantic lint — LLM contradiction detection over `answers/` + `decisions.md` | W5 |
| 20 | Adaptive chunk size and overlap | C2 |
| 21 | **Migrate to `bibtexparser>=2.0`** — v1.4 silently drops malformed BibTeX entries common in ACM/AAAI/IJCAI proceedings | X33 |
| 22 | Diagram OCR — GPT-4o-vision pass on architecture figures | P2 |
| 23 | HTML wiki viewer — single-page browser (beyond Obsidian) | — |
| 24 | Hook auto-fix — `wiki-lint` moves from warn-only to fix-with-confirmation | W5 |
| 25 | **Switch community detection to `python-igraph` + `leidenalg`** — 5–20× faster than NetworkX Louvain; Leiden avoids the resolution-limit merging problem; prerequisite for multi-paper compile at scale | X28, X29, CM1 |
| 26 | Run the PaperBench evaluation from `docs/05` | V1, V2, V3 |
| 27 | Semantic intent detection — replace `detect-intent.sh` bash regex | SK1 |
| 28 | **FTS5 domain-specific synonym expansion** — pre-expand scientific terms to close lexical recall gap on physics/chemistry queries | X31 |
| 29 | **Fix overlap dedup dead code** — remove the `and chunk in deduped[-1]` condition in `split_with_overlap:205`; one-line fix | C8 |
| 30 | **`paper-compiler prefetch` command** — pre-download model weights before a build | X24 |
| 31 | Implement `cache prune` | I1 |
| 32 | **Demote Unpaywall in source order** — move after OpenAlex; better coverage, single-lookup path | X20 |
| 33 | **S2 circuit-breaker** — abort after 3 consecutive 5xx failures with a clear message | X35 |
| 34 | Memory-plane GC — rotate `sessions/` and compact `decisions.md` | W3 |

---

*Update this file on every v2.x release. Cross-reference to `v1_build.md` and `v2_build.md` for the full context on each item.*
