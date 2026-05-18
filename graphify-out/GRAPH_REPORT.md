# Graph Report - .  (2026-05-18)

## Corpus Check
- 80 files · ~58,934 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 542 nodes · 837 edges · 50 communities detected
- Extraction: 88% EXTRACTED · 12% INFERRED · 0% AMBIGUOUS · INFERRED: 100 edges (avg confidence: 0.52)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Skill Ecosystem & research Artifacts|Skill Ecosystem & research/ Artifacts]]
- [[_COMMUNITY_MCP Graph Wrapper|MCP Graph Wrapper]]
- [[_COMMUNITY_Pipeline Orchestrator|Pipeline Orchestrator]]
- [[_COMMUNITY_Architecture Rationale (docs)|Architecture Rationale (docs)]]
- [[_COMMUNITY_Architecture Concepts|Architecture Concepts]]
- [[_COMMUNITY_MCP Hybrid Retrieval DB|MCP Hybrid Retrieval DB]]
- [[_COMMUNITY_Paper Acquisition|Paper Acquisition]]
- [[_COMMUNITY_LLM Backend Selection|LLM Backend Selection]]
- [[_COMMUNITY_Community Detection & Wiki Render|Community Detection & Wiki Render]]
- [[_COMMUNITY_Graph DB Ingestion|Graph DB Ingestion]]
- [[_COMMUNITY_Config Loader|Config Loader]]
- [[_COMMUNITY_Atom Extraction|Atom Extraction]]
- [[_COMMUNITY_LaTeX Parser|LaTeX Parser]]
- [[_COMMUNITY_Prose Quality Filtering|Prose Quality Filtering]]
- [[_COMMUNITY_Atom Deduplication|Atom Deduplication]]
- [[_COMMUNITY_Eval Protocol Driver|Eval Protocol Driver]]
- [[_COMMUNITY_Audit Checklist Categories|Audit Checklist Categories]]
- [[_COMMUNITY_Rubric Auto-Grader|Rubric Auto-Grader]]
- [[_COMMUNITY_Incremental Ingest|Incremental Ingest]]
- [[_COMMUNITY_CLI Dispatch|CLI Dispatch]]
- [[_COMMUNITY_Cache Layer|Cache Layer]]
- [[_COMMUNITY_Graph JSON Renderer|Graph JSON Renderer]]
- [[_COMMUNITY_Paper Resolver|Paper Resolver]]
- [[_COMMUNITY_Paper Scoring|Paper Scoring]]
- [[_COMMUNITY_Heuristic Edge Classifier|Heuristic Edge Classifier]]
- [[_COMMUNITY_Embedding Writer|Embedding Writer]]
- [[_COMMUNITY_research.md Renderer|research.md Renderer]]
- [[_COMMUNITY_Wiki Append-Only Log|Wiki Append-Only Log]]
- [[_COMMUNITY_Eval Analysis & CIs|Eval Analysis & CIs]]
- [[_COMMUNITY_Atom Schema|Atom Schema]]
- [[_COMMUNITY_Parse Dispatcher|Parse Dispatcher]]
- [[_COMMUNITY_Human Grader|Human Grader]]
- [[_COMMUNITY_LLM Edge Classifier|LLM Edge Classifier]]
- [[_COMMUNITY_PDF Parser (Marker)|PDF Parser (Marker)]]
- [[_COMMUNITY_Schema Doc Generator|Schema Doc Generator]]
- [[_COMMUNITY_Wiki Schema Doc|Wiki Schema Doc]]
- [[_COMMUNITY_MCP Server Init|MCP Server Init]]
- [[_COMMUNITY_Build Manifest Writer|Build Manifest Writer]]
- [[_COMMUNITY_Evidence Files Writer|Evidence Files Writer]]
- [[_COMMUNITY_Missing Details Writer|Missing Details Writer]]
- [[_COMMUNITY_Eval Conditions|Eval Conditions]]
- [[_COMMUNITY_Failure & Risk Tables|Failure & Risk Tables]]
- [[_COMMUNITY_Eval Sample Definitions|Eval Sample Definitions]]
- [[_COMMUNITY_CLI Package Init|CLI Package Init]]
- [[_COMMUNITY_CLI Main Entry|CLI Main Entry]]
- [[_COMMUNITY_Classify Package Init|Classify Package Init]]
- [[_COMMUNITY_Render Package Init|Render Package Init]]
- [[_COMMUNITY_Eval Package Init|Eval Package Init]]
- [[_COMMUNITY_Grader Package Init|Grader Package Init]]
- [[_COMMUNITY_Config Loading Order Doc|Config Loading Order Doc]]

## God Nodes (most connected - your core abstractions)
1. `use-research-context (skill)` - 34 edges
2. `ResearchGraph` - 30 edges
3. `Config` - 27 edges
4. `wiki-query (skill)` - 21 edges
5. `S2Client` - 20 edges
6. `audit-against-research (skill)` - 15 edges
7. `build-research-context (skill)` - 14 edges
8. `Candidate` - 12 edges
9. `_graph()` - 11 edges
10. `Paper` - 11 edges

## Surprising Connections (you probably didn't know these)
- `Rubric JSON schema (per-paper leaf tasks)` --semantically_similar_to--> `11-role citation edge label set`  [INFERRED] [semantically similar]
  eval/rubric/schema.md → docs/01-PRD.md
- `LLM grader (Claude Sonnet 4.6, temperature 0).  For leaves with `check_type == "` --uses--> `Config`  [INFERRED]
  eval/grader/llm.py → plugin-scaffold/cli/src/paper_compiler_cli/config.py
- `Incremental ingest: add one paper to an existing compiled corpus.  Used by `/pap` --uses--> `Config`  [INFERRED]
  plugin-scaffold/cli/src/paper_compiler_cli/ingest.py → plugin-scaffold/cli/src/paper_compiler_cli/config.py
- `Wrap DB records in the {metadata, …} shape `write_wiki` expects.` --uses--> `Config`  [INFERRED]
  plugin-scaffold/cli/src/paper_compiler_cli/ingest.py → plugin-scaffold/cli/src/paper_compiler_cli/config.py
- `Return ``"anthropic"``, ``"claude_cli"``, or ``None``.` --uses--> `Config`  [INFERRED]
  plugin-scaffold/cli/src/paper_compiler_cli/llm.py → plugin-scaffold/cli/src/paper_compiler_cli/config.py

## Hyperedges (group relationships)
- **Three-plane separation (CLI writes / research/ artifact / MCP reads)** — readme_cli_9_stages, readme_research_dir_artifact, readme_mcp_server_15_tools, arch_three_runtime_planes, claudemd_three_plane_invariant [EXTRACTED 1.00]
- **A/B/C evaluation protocol across hypothesis, eval plan, and ship gate** — readme_hypothesis_abc, eval_three_conditions_abc, eval_paper_sample_20, eval_replication_score_metric, eval_ship_gate_criteria [EXTRACTED 1.00]
- **Three skills compose the user-facing plugin surface** — plugin_guide_skill_build, plugin_guide_skill_use, plugin_guide_skill_audit, readme_mcp_server_15_tools [EXTRACTED 1.00]
- **use-research-context implementation-task playbook family** — ref_use_research_context_implementing_architecture, ref_use_research_context_implementing_dataset, ref_use_research_context_implementing_eval, ref_use_research_context_implementing_baseline, ref_use_research_context_implementing_loss, ref_use_research_context_debugging_mismatch, skill_use_research_context [EXTRACTED 1.00]
- **Audit checklist categories implementing the verdict acceptance gate set** — audit_category_architecture, audit_category_loss, audit_category_dataset, audit_category_preprocessing, audit_category_evaluation, audit_category_baseline, audit_category_optimizer, audit_category_hyperparameter, audit_verdicts [EXTRACTED 1.00]
- **Wiki skill family (ingest -> query -> lint)** — skill_wiki_ingest, skill_wiki_query, skill_wiki_lint [INFERRED 0.90]

## Communities

### Community 0 - "Skill Ecosystem & research/ Artifacts"
Cohesion: 0.05
Nodes (62): audit-report.md, research/build-manifest.json, research/evidence/, research/graph.json, research/missing-details.md, research/research.db (Graph RAG sqlite store), research/research.md (compiled brief), research/SCHEMA.md (+54 more)

### Community 1 - "MCP Graph Wrapper"
Cohesion: 0.07
Nodes (45): _atom_text(), _Indexes, load(), _load_embedder(), ResearchGraph, _tokenize(), citation_neighbors(), community_summary() (+37 more)

### Community 2 - "Pipeline Orchestrator"
Cohesion: 0.11
Nodes (37): BaseModel, Community detection + LLM summarization for the implementation atom graph.  Buil, # IMPORTANT: model must match chunks_vec dim (384). bge-small is, Config, ClassifiedEdge, _acquire_neighborhood(), _build_raw_edges(), expand_neighborhood() (+29 more)

### Community 3 - "Architecture Rationale (docs)"
Cohesion: 0.05
Nodes (45): Three content-addressed caches, Milestones M0-M6 (build order), Architecture optimizes for evidence + cheap compiles + replaceability (rationale), S2 rate-limit + token bucket, Plane-separation rationale (why CLI never serves), Three runtime planes (compile/storage/query), Changelog v0.1.0 (2026-05-17), Known sharp edges (v0.2) (+37 more)

### Community 4 - "Architecture Concepts"
Cohesion: 0.07
Nodes (30): Atom graph schema, Frontier expansion policy (Stage 4), Hybrid heuristic+LLM edge classifier (Stage 5), Implementation atom (graph node), IR Schema (paper intermediate representation), LLM backend selection (claude_cli > Anthropic SDK > none), CLI entry points (compile.py:build_paper), Atom coverage metric (+22 more)

### Community 5 - "MCP Hybrid Retrieval DB"
Cohesion: 0.11
Nodes (21): _diversity_rerank(), _embed(), _embedder(), _is_atom(), _is_paper(), neighborhood_subgraph(), open_ro(), paper_text() (+13 more)

### Community 6 - "Paper Acquisition"
Cohesion: 0.13
Nodes (10): acquire(), Acquired, _download(), _extract_tar(), _now(), RuntimeError, S2Client, S2Error (+2 more)

### Community 7 - "LLM Backend Selection"
Cohesion: 0.16
Nodes (17): Exception, _call_anthropic(), _call_claude_cli(), call_llm(), grade_leaf(), _has_anthropic_sdk(), _has_claude_cli(), llm_backend() (+9 more)

### Community 8 - "Community Detection & Wiki Render"
Cohesion: 0.25
Nodes (14): _build_graph(), Community, _detect(), detect_and_summarize(), _summarize_llm(), _atom_link(), _paper_link(), llm-wiki style article generator.  Karpathy's /raw → llm-wiki pattern, scoped to (+6 more)

### Community 9 - "Graph DB Ingestion"
Cohesion: 0.13
Nodes (10): _chunk_paragraphs(), ingest_paper(), open_db(), Graph RAG database — single sqlite file with sqlite-vec + FTS5.  Layout (one ``r, Yield (chunk_anchor_id, cleaned_text, paragraph_id) per chunk.      Splits long, Insert a parsed Paper IR. Returns chunk row IDs created., Insert chunk embeddings (numpy array N×D) into chunks_vec., Open / create the graph DB. Returns (conn, vec_loaded). (+2 more)

### Community 10 - "Config Loader"
Cohesion: 0.18
Nodes (11): apply_overrides(), CacheConfig, CompileConfig, LLMConfig, load_config(), _load_dotenv(), _merge(), OutputConfig (+3 more)

### Community 11 - "Atom Extraction"
Cohesion: 0.33
Nodes (11): _atom_id(), _evidence_id(), extract_atoms(), _extract_for_paper(), _find_defining_paper(), _is_junk_name(), _llm_extract(), _ngram() (+3 more)

### Community 12 - "LaTeX Parser"
Cohesion: 0.26
Nodes (7): _expand_inputs(), _find_main_tex(), _iter_nodes(), _load_bib(), _load_thebibliography(), _macro_text(), parse_tex()

### Community 13 - "Prose Quality Filtering"
Cohesion: 0.22
Nodes (10): is_indexable(), is_method_adjacent_title(), prose_quality(), Shared text utilities: placeholder scrubbing + prose quality scoring.  These fun, Decide whether a chunk should be inserted into ``chunks_fts``.      Returns (is_, Split long text into overlapping windows of roughly ``target_chars``.      Split, Strip LaTeX / Marker placeholders. Collapse whitespace., Return a 0..1 score for "looks like English prose" vs table/equation noise. (+2 more)

### Community 14 - "Atom Deduplication"
Cohesion: 0.38
Nodes (10): _containment(), deduplicate(), _embedding_pass(), _exact_normalize(), _jaccard(), _jaccard_pass(), _merge(), Atom deduplication.  Existing per-paragraph extraction yields many near-duplicat (+2 more)

### Community 15 - "Eval Protocol Driver"
Cohesion: 0.33
Nodes (9): _compile_paper(), _condition_env(), _git_init(), _install_plugin(), _launch_session(), main(), Eval protocol driver.  For each paper × condition: fresh repo, plugin install (B, Launch a Claude Code session in headless mode.      The actual harness depends o (+1 more)

### Community 16 - "Audit Checklist Categories"
Cohesion: 0.2
Nodes (10): Audit category: architecture, Audit category: baseline, Audit category: dataset, Audit category: evaluation, Audit category: hyperparameter, Audit category: loss, Audit category: optimizer / training_trick, Audit category: preprocessing (+2 more)

### Community 17 - "Rubric Auto-Grader"
Cohesion: 0.31
Nodes (6): check_function_signature(), check_import_or_class(), grade_paper(), main(), Programmatic rubric grader.  Reads `eval/rubric/<slug>.json` and a run repo, emi, _walk_python()

### Community 18 - "Incremental Ingest"
Cohesion: 0.39
Nodes (7): ingest_paper_into_research(), _load_atoms_from_db(), _load_evidence_from_db(), _load_paper_records_from_db(), Incremental ingest: add one paper to an existing compiled corpus.  Used by `/pap, Wrap DB records in the {metadata, …} shape `write_wiki` expects., _wiki_papers_dict()

### Community 19 - "CLI Dispatch"
Cohesion: 0.29
Nodes (2): _candidates_to_json(), cmd_resolve()

### Community 20 - "Cache Layer"
Cohesion: 0.48
Nodes (6): paper_source_dir(), parsed_ir_path(), s2_cache_get(), s2_cache_path(), s2_cache_put(), _safe_id()

### Community 21 - "Graph JSON Renderer"
Cohesion: 0.52
Nodes (6): _atom_node(), build_graph_doc(), _edge_node(), _evidence_node(), _missing_node(), _paper_node()

### Community 22 - "Paper Resolver"
Cohesion: 0.8
Nodes (4): _from_record(), _normalize(), resolve(), _resolve_local()

### Community 23 - "Paper Scoring"
Cohesion: 0.6
Nodes (3): _implementation(), _scholarly(), score_papers()

### Community 24 - "Heuristic Edge Classifier"
Cohesion: 0.6
Nodes (4): best_role(), classify_edges(), is_implementation_critical(), _top_confidence()

### Community 25 - "Embedding Writer"
Cohesion: 0.6
Nodes (4): _atom_text(), _load_embedder(), Persist atom embeddings for the MCP server's vector search.  Writes ``research/e, write_embeddings()

### Community 26 - "research.md Renderer"
Cohesion: 0.7
Nodes (4): _atom_block(), _count(), render_research_md(), _tldr()

### Community 27 - "Wiki Append-Only Log"
Cohesion: 0.6
Nodes (4): append_log(), log_compile(), _now_iso(), Append-only `research/wiki/log.md` writer.  Karpathy's llm-wiki uses a chronolog

### Community 28 - "Eval Analysis & CIs"
Cohesion: 0.6
Nodes (4): _bootstrap_ci(), main(), _per_paper_scores(), Replication score, deltas, bootstrap CIs.  Reads the grades CSV and emits a wide

### Community 29 - "Atom Schema"
Cohesion: 0.5
Nodes (3): Atom, EvidenceSpan, MissingDetail

### Community 30 - "Parse Dispatcher"
Cohesion: 0.83
Nodes (3): _empty_paper(), _metadata_from_candidate(), parse_paper()

### Community 31 - "Human Grader"
Cohesion: 0.67
Nodes (3): _kappa(), main(), Human grader CLI for the 10% audit sample.  Stratifies the grades CSV by (paper,

### Community 32 - "LLM Edge Classifier"
Cohesion: 1.0
Nodes (2): _build_user(), classify_llm()

### Community 33 - "PDF Parser (Marker)"
Cohesion: 1.0
Nodes (2): _markdown_from_marker(), parse_pdf()

### Community 34 - "Schema Doc Generator"
Cohesion: 0.67
Nodes (1): Emit research/SCHEMA.md — the schema reference Claude reads to learn the DB.  Ke

### Community 35 - "Wiki Schema Doc"
Cohesion: 0.67
Nodes (1): Emit `research/wiki/SCHEMA.md` — contract for the wiki article tree.  This is *n

### Community 36 - "MCP Server Init"
Cohesion: 1.0
Nodes (1): paper-compiler MCP server.

### Community 37 - "Build Manifest Writer"
Cohesion: 1.0
Nodes (0): 

### Community 38 - "Evidence Files Writer"
Cohesion: 1.0
Nodes (0): 

### Community 39 - "Missing Details Writer"
Cohesion: 1.0
Nodes (0): 

### Community 40 - "Eval Conditions"
Cohesion: 1.0
Nodes (1): Condition

### Community 41 - "Failure & Risk Tables"
Cohesion: 1.0
Nodes (2): Failure-mode handling table, Risks & mitigations table

### Community 42 - "Eval Sample Definitions"
Cohesion: 1.0
Nodes (2): 5-paper dev sample, Eval preconditions (when not to run)

### Community 43 - "CLI Package Init"
Cohesion: 1.0
Nodes (0): 

### Community 44 - "CLI Main Entry"
Cohesion: 1.0
Nodes (0): 

### Community 45 - "Classify Package Init"
Cohesion: 1.0
Nodes (0): 

### Community 46 - "Render Package Init"
Cohesion: 1.0
Nodes (0): 

### Community 47 - "Eval Package Init"
Cohesion: 1.0
Nodes (0): 

### Community 48 - "Grader Package Init"
Cohesion: 1.0
Nodes (0): 

### Community 49 - "Config Loading Order Doc"
Cohesion: 1.0
Nodes (1): Config loading order

## Knowledge Gaps
- **112 isolated node(s):** `Sqlite-backed Graph RAG helpers used by the MCP server.  The DB is built by pape`, `Maximum Marginal Relevance-ish: drop near-duplicates by paper_id.      We don't`, `Hybrid BM25 + sqlite-vec chunk search with MMR-style diversification.      Retur`, `Return chunks of one paper grouped by section.      Default (``full=False``) yie`, `Read-only SQL escape hatch. Refuses anything but SELECT/WITH.` (+107 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `MCP Server Init`** (2 nodes): `paper-compiler MCP server.`, `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Build Manifest Writer`** (2 nodes): `write_manifest()`, `build_manifest.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Evidence Files Writer`** (2 nodes): `write_evidence_files()`, `evidence_files.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Missing Details Writer`** (2 nodes): `write_missing_details()`, `missing_details.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Eval Conditions`** (2 nodes): `Condition`, `conditions.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Failure & Risk Tables`** (2 nodes): `Failure-mode handling table`, `Risks & mitigations table`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Eval Sample Definitions`** (2 nodes): `5-paper dev sample`, `Eval preconditions (when not to run)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `CLI Package Init`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `CLI Main Entry`** (1 nodes): `__main__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Classify Package Init`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Render Package Init`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Eval Package Init`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Grader Package Init`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Config Loading Order Doc`** (1 nodes): `Config loading order`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Config` connect `Pipeline Orchestrator` to `Paper Acquisition`, `LLM Backend Selection`, `Community Detection & Wiki Render`, `Config Loader`, `Incremental Ingest`?**
  _High betweenness centrality (0.048) - this node is a cross-community bridge._
- **Why does `Run heuristic + (budgeted) LLM atom extraction on one paper's method sections.` connect `Pipeline Orchestrator` to `Atom Extraction`?**
  _High betweenness centrality (0.014) - this node is a cross-community bridge._
- **Why does `Community` connect `Community Detection & Wiki Render` to `Pipeline Orchestrator`?**
  _High betweenness centrality (0.013) - this node is a cross-community bridge._
- **Are the 18 inferred relationships involving `ResearchGraph` (e.g. with `paper-compiler MCP server.  Reads research/graph.json compiled by the CLI and ex` and `Return metadata and a list of implementation atoms defined or used by this paper`) actually correct?**
  _`ResearchGraph` has 18 INFERRED edges - model-reasoned connections that need verification._
- **Are the 25 inferred relationships involving `Config` (e.g. with `Community` and `Community detection + LLM summarization for the implementation atom graph.  Buil`) actually correct?**
  _`Config` has 25 INFERRED edges - model-reasoned connections that need verification._
- **Are the 9 inferred relationships involving `S2Client` (e.g. with `Config` and `Candidate`) actually correct?**
  _`S2Client` has 9 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Sqlite-backed Graph RAG helpers used by the MCP server.  The DB is built by pape`, `Maximum Marginal Relevance-ish: drop near-duplicates by paper_id.      We don't`, `Hybrid BM25 + sqlite-vec chunk search with MMR-style diversification.      Retur` to the rest of the system?**
  _112 weakly-connected nodes found - possible documentation gaps or missing edges._