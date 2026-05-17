# paper-compiler — Claude Code plugin scaffold

> Compile a research paper and its citation neighborhood into an implementation-ready memory for Claude Code.

**Status:** v0.1 scaffold. Wiring works; the real compile pipeline and graph queries are stubs. See `../docs/` for the full plans.

---

## What this is

A Claude Code plugin that, given a research paper, produces a `research/` directory containing:

- `research.md` — a concise implementation brief.
- `missing-details.md` — open questions and assumptions.
- `graph.json` — the implementation atom graph.
- `evidence/<atom-id>.md` — per-claim evidence spans.

And a bundled MCP server that exposes the graph as queryable tools (`trace_dependency`, `find_atom`, `get_evidence`, etc.) for Claude Code to use while writing code.

---

## Why a plugin (and not just a script)

Because the value is in the workflow, not the artifacts. The plugin packages:

- **Skills** that tell Claude Code when to compile, when to consult, and when to audit.
- An **MCP server** that exposes the compiled graph as structured tools.
- A **subagent** (the build skill running with `context: fork`) so the heavy work doesn't pollute the main session.
- A **hook** (warn-only in v0.1) that flags work touching unresolved assumptions.

A naked CLI would skip all of that and force the user to glue it together themselves.

---

## Quick start (scaffold mode)

From the parent directory of this scaffold:

```bash
# 1. Enter a fresh test repository.
cd /tmp && mkdir test-paper && cd test-paper && git init

# 2. Launch Claude Code with the plugin loaded.
claude --plugin-dir /path/to/paper-compiler/plugin-scaffold
```

In the Claude Code session:

```
/paper-compiler:build-research-context arxiv:2310.06825
```

In scaffold mode this will produce a placeholder `research/research.md` and a stub `graph.json`. The MCP tools (`mcp__paper-compiler__*`) will return `_scaffold: true` responses.

---

## Directory layout

```
plugin-scaffold/
├── .claude-plugin/
│   └── plugin.json                       # Plugin manifest
├── skills/
│   ├── build-research-context/SKILL.md   # Manual-invoke compile
│   ├── use-research-context/SKILL.md     # Auto-invoke during implementation
│   └── audit-against-research/SKILL.md   # Auto-invoke during review
├── hooks/
│   └── hooks.json                        # Warn-only PreToolUse hook
├── .mcp.json                             # MCP server declaration
├── server/                               # Bundled MCP server (Python)
│   ├── pyproject.toml
│   └── src/paper_compiler_mcp/
│       ├── __init__.py
│       └── server.py
├── cli/                                  # CLI invoked by the build skill
│   └── bin/paper-compiler                # Stub for now
├── scripts/
│   └── check-assumptions.sh              # Hook script (warn-only)
├── CLAUDE.md                             # Plugin-scoped system instructions
└── README.md                             # This file
```

See `../docs/03-claude-code-plugin-guide.md` for the rationale behind every directory.

---

## Building the real thing

Don't replace the scaffold all at once. The build order in `../docs/04-architecture.md §11` is:

1. **M0 (weeks 1–2):** scaffold loads in Claude Code; skills appear; MCP tools list correctly. *(This is what's in this repo today.)*
2. **M1 (weeks 3–4):** real `resolve` + `acquire` + parse → IR for one paper.
3. **M2 (weeks 5–7):** citation expansion + heuristic+LLM edge classifier.
4. **M3 (weeks 8–10):** atom graph + real `research.md`.
5. **M4 (weeks 11–12):** real MCP server backed by `graph.json`.
6. **M5 (weeks 13–14):** polish, marketplace.json, end-to-end self-compile.
7. **M6 (weeks 15–16):** A/B evaluation per `../docs/05-evaluation-plan.md`.

The key discipline: **don't move on until the previous milestone's exit criteria are green.** It is much cheaper to find wiring bugs at M0 than to find them tangled with parser bugs at M3.

---

## Configuration

When the real CLI exists, it'll read `paper-compiler.toml` from the project root or `~/.config/paper-compiler/config.toml`. Schema:

```toml
[s2]
api_key = "..."                  # or SEMANTIC_SCHOLAR_API_KEY env var

[compile]
max_depth = 2
max_papers = 200
max_s2_requests = 500
max_wall_seconds = 1200
classifier_llm_max_calls = 50

[parser]
prefer = "tex"                   # "tex" | "pdf"
pdf_backend = "grobid"           # "grobid" | "marker" | "nougat" | "mineru"
grobid_url = "http://localhost:8070"

[output]
research_dir = "research"
research_md_max_tokens = 8000

[cache]
dir = "~/.cache/paper-compiler"
ttl_metadata_days = 30
```

---

## Where things live (one-line reference)

- **What we're building and why** → `../docs/01-PRD.md`
- **Prior work and reading order** → `../docs/02-research-context.md`
- **How Claude Code plugin/skill/MCP/subagent fits together** → `../docs/03-claude-code-plugin-guide.md`
- **System architecture and data model** → `../docs/04-architecture.md`
- **A/B evaluation protocol** → `../docs/05-evaluation-plan.md`

---

## License

TODO — MIT recommended.
