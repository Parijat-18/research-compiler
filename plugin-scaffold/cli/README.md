# paper-compiler CLI

Compiles a paper + its citation neighborhood into a `research/` directory consumed by the bundled MCP server.

## Install

```bash
pip install -e .                # core: resolve + tex parse + neighborhood + heuristic classifier
pip install -e ".[pdf]"         # add Marker for PDF papers
pip install -e ".[indexes]"     # add rank-bm25 + sentence-transformers for vector search
pip install -e ".[full]"        # everything
```

## Environment

- `SEMANTIC_SCHOLAR_API_KEY` — strongly recommended. Without it, you share the public 5,000-req-per-5-min pool.
- `ANTHROPIC_API_KEY` — required for the LLM classifier residual and LLM atom extraction.

## Commands

```bash
paper-compiler resolve arxiv:2310.06825
paper-compiler parse arxiv:2310.06825 --out /tmp/paper.json
paper-compiler build arxiv:2310.06825 --out research/
paper-compiler build arxiv:2310.06825 --out research/ --refresh
paper-compiler cache prune --older-than 90d
```

`build` is the long step (5–20 min on a typical ML paper). Watch stderr for stage progress.

## Config

A `paper-compiler.toml` in the working directory (or `~/.config/paper-compiler/config.toml`) overrides defaults. Example:

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

## Outputs (under `research/`)

- `research.md` — the brief (≤ 8000 tokens).
- `missing-details.md` — explicit open questions.
- `graph.json` — full implementation atom graph (MCP server reads this).
- `evidence/<atom-id>.md` — per-atom verbatim evidence packs.
- `build-manifest.json` — counts, coverage, failures, wall time.

## Pipeline (architecture doc §3)

1. Resolve. 2. Acquire. 3. Parse → IR. 4. Expand neighborhood. 5. Classify edges. 6. Build atom graph. 7. Score. 8. Index. 9. Render.

Stages 4–9 read only the IR; the source PDF/TeX is never read after stage 3.
