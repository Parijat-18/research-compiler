# Changelog

## 0.1.0 — 2026-05-17

Initial v1 release.

### Compile pipeline (CLI)

- Stage 1 resolve: arXiv / DOI / S2 ID / URL / local file → canonical S2 paper ID.
- Stage 2 acquire: arXiv e-print tarball → S2 `openAccessPdf` → user local file.
- Stage 3 parse: TeX path via `pylatexenc` + `bibtexparser`; PDF path via Marker (`marker-pdf`, optional extra).
- Stage 4 expand: priority-driven frontier policy with `expand_top_k=20`, depth-2 default, hard caps on papers / S2 requests / wall time.
- Stage 5 classify: hybrid edge classifier — section-typed heuristic with text hints, then Anthropic LLM (Haiku 4.5, temperature 0) for low-confidence residual, capped at 50 calls.
- Stage 6 atom extraction: rule-based scan over Method section paragraphs + LLM extraction per paragraph (Haiku, cap 80 calls), with experiments/results sections mining for dataset/baseline/evaluation atoms.
- Stage 7 score: `0.7 * implementation_influence + 0.3 * scholarly_influence`, topological order by category + dependencies.
- Stage 9 render: `research.md` (8k token budget, `tiktoken`), `missing-details.md`, `graph.json`, `evidence/<atom-id>.md`, `build-manifest.json`.

### MCP server

- Lazy-loads `research/graph.json` on first tool call (cold start <2s).
- All nine PRD §13 tools implemented against `ResearchGraph`.
- BM25 search via `rank-bm25`; optional vector search via `sentence-transformers` (SPECTER2, fallback `bge-small-en-v1.5`).

### Plugin shell

- Three skills: `build-research-context` (manual + forked subagent), `use-research-context` (auto), `audit-against-research` (auto).
- Warn-only PreToolUse hook over Write/Edit that flags unacknowledged assumptions.

### Evaluation

- `eval/` harness scaffolded per `docs/05-evaluation-plan.md` — protocol driver, rubric format, automated/LLM/human graders, analysis.
