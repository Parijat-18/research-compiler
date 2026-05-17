# Claude Code Plugin Guide — Building `paper-compiler`

**Audience:** the engineer building this plugin.
**Assumed knowledge:** you have used Claude Code, but you have never shipped a plugin.
**Scope:** everything you need to package and ship the Research Compiler as a Claude Code plugin, including skills, MCP server, subagents, and hooks.

This document is **opinionated** — it picks one shape for the plugin and tells you to build that one. The reasoning behind each choice is in the PRD; this doc is the how-to.

---

## 1. Mental model — what each primitive actually is

Read this section once and refer back. The terms get used interchangeably elsewhere on the internet, and they are not the same thing.

| Primitive | What it is | When you reach for it |
|---|---|---|
| **Plugin** | A versioned, installable package that bundles everything below. Has a `.claude-plugin/plugin.json` manifest. | When you want a workflow reusable across repositories. |
| **Skill** | A `SKILL.md` file with YAML frontmatter that teaches the agent a procedure. Discovered automatically by name + description; also invocable as `/plugin-name:skill-name`. | When you keep pasting the same instructions / checklist into chat. |
| **MCP server** | An external process (or a bundled one) that exposes structured tools over the Model Context Protocol. Tools appear in Claude's toolkit. | When you have stateful, queryable, structured data the agent should fetch from rather than reason about. |
| **Subagent** | A forked agent run with its own context window. Skills with `context: fork` launch a subagent. | When a task would pollute the main context (heavy exploration, long research, audit). |
| **Hook** | A handler that fires on specific lifecycle events (PreToolUse, PostToolUse, UserPromptSubmit, etc.). | When you want guardrails or automatic actions independent of model choice. |
| **Slash command** | Sugar over skills. A skill named `foo` is invocable as `/plugin-name:foo`. The older standalone-command directory still works but the recommended path is skills. |

The rule we will follow:

- **Skills** are how we *steer* Claude (workflow, rules, what to do when).
- **MCP tools** are how Claude *retrieves structured data* from the compiled corpus.
- **Subagents** are how we *isolate context* for heavy work (the compile itself).
- **Hooks** are an *optional* guardrail (e.g. block commits if `missing-details.md` is unresolved).
- **The plugin** is the *package* that ships all of the above.

---

## 2. The directory layout we will use

```
paper-compiler/
├── .claude-plugin/
│   └── plugin.json              # Plugin manifest. ONLY file in this directory.
├── skills/
│   ├── build-research-context/
│   │   ├── SKILL.md             # Manual-invoke compile
│   │   └── references/          # Optional support docs the skill can read
│   ├── use-research-context/
│   │   └── SKILL.md             # Auto-invoke during implementation
│   └── audit-against-research/
│       └── SKILL.md             # Auto-invoke during review / completion
├── agents/
│   └── research-explorer.md     # Subagent definition (optional sibling to skills)
├── hooks/
│   └── hooks.json               # Optional guardrails (warn / block on drift)
├── .mcp.json                    # Declares the bundled MCP server(s)
├── scripts/
│   └── ...                      # Helper scripts callable by skills/MCP
├── server/                       # The bundled MCP server source
│   ├── pyproject.toml
│   └── src/
│       └── paper_compiler_mcp/
│           ├── __init__.py
│           ├── server.py
│           └── tools/
├── cli/                          # The compile CLI (called by the build skill)
│   ├── pyproject.toml
│   └── src/paper_compiler_cli/
├── CLAUDE.md                    # System instructions when this plugin is installed
└── README.md
```

Notes:

- **`.claude-plugin/plugin.json` is required.** All other directories are optional and auto-discovered when they exist.
- **Use kebab-case for everything** — skill names, file names, agent names. The marketplace and slash-command surface depend on it.
- **The MCP server lives inside the plugin repo** (`server/`) and is referenced from `.mcp.json` via `${CLAUDE_PLUGIN_ROOT}`. Never hardcode absolute paths.
- The CLI and the MCP server are intentionally separate codebases under one repo. The CLI does *compile-time* work. The MCP server does *runtime* read-only queries.

---

## 3. `plugin.json` manifest

Minimal but complete:

```json
{
  "name": "paper-compiler",
  "description": "Compile a research paper and its citation neighborhood into an implementation-ready memory for Claude Code.",
  "version": "0.1.0",
  "author": {
    "name": "Your Name",
    "email": "you@example.com"
  },
  "homepage": "https://github.com/your-org/paper-compiler",
  "repository": "https://github.com/your-org/paper-compiler",
  "license": "MIT",
  "keywords": ["research", "papers", "reproducibility", "rag", "mcp"]
}
```

You do **not** need to declare `skills`, `agents`, or `hooks` paths if you use the standard directory layout — they are auto-discovered.

---

## 4. Skills — the three we ship

### 4.1 `build-research-context` — manual-invoke compile

This is the heavyweight action. You want a human in the loop before it runs. Set `disable-model-invocation: true` so Claude can never auto-trigger it.

**File:** `skills/build-research-context/SKILL.md`

```markdown
---
name: build-research-context
description: Manually invoked. Compiles a target paper and its citation neighborhood into a research/ directory with research.md, missing-details.md, an implementation atom graph, and per-atom evidence. Use only when the user explicitly asks to build, compile, ingest, or refresh research context for a paper.
disable-model-invocation: true
context: fork
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
---

# Build research context for a paper

You are running as a forked subagent. The main Claude Code session will not see your intermediate work — only your final report. Make your final report tight: paths to the generated files, a one-paragraph summary, and any errors.

## Inputs

The user has invoked `/paper-compiler:build-research-context <ID-or-URL>`. The `<ID-or-URL>` is one of:

- An arXiv ID (`2310.XXXXX`)
- A DOI
- A Semantic Scholar paper ID
- A URL to any of the above
- A local PDF or TeX tarball path

## Procedure

1. **Resolve.** Run `${CLAUDE_PLUGIN_ROOT}/cli/bin/paper-compiler resolve <input>` and read the output to confirm the canonical paper.
2. **Confirm with user if ambiguous.** If `resolve` returned multiple candidates, ask the user which one. Do not proceed on a guess.
3. **Compile.** Run `${CLAUDE_PLUGIN_ROOT}/cli/bin/paper-compiler build <paper-id> --out research/`. This is the long step.
4. **Read the build manifest.** After `build` exits, read `research/build-manifest.json`. It contains stats, errors, and coverage numbers.
5. **Report back.** Produce a final report following the template below.

## Final report template

```
Compiled <paper title>.

Outputs:
- research/research.md
- research/missing-details.md
- research/graph.json
- research/evidence/

Coverage: <N>/<M> references resolved (<pct>%).
Failed acquisitions: <list>
Open implementation questions: <count> — see research/missing-details.md.

Next: review research.md, then ask me to implement.
```

## Rules

- Never run `build` without first running `resolve` and surfacing the canonical paper.
- Never edit `research/` files yourself. The CLI is the only writer.
- If `build` fails, do not retry blindly. Read the error, surface it, ask the user.
- Do not summarise the paper's contents in your report. The summary lives in `research.md`. Your job is to confirm the compile completed.
```

### 4.2 `use-research-context` — auto-invoke during implementation

Short, sharp, in-context. Auto-invocable so Claude reaches for it whenever the user is implementing in a repo that has a compiled brief.

**File:** `skills/use-research-context/SKILL.md`

```markdown
---
name: use-research-context
description: Use this skill whenever the user asks to implement, port, reproduce, modify, or extend code from a research paper in a repository that contains a research/ directory with research.md. This skill instructs you to consult the compiled research context before writing implementation code and to query the paper-compiler MCP tools for any specific implementation decision.
allowed-tools:
  - Read
  - mcp__paper-compiler__*
---

# Use compiled research context for paper implementation

## Trigger

Activate when **both** are true:

1. The user is asking for implementation work that originates from a paper.
2. The current repository contains `research/research.md`.

If only (1) is true and there is no `research/`, tell the user a research context has not been compiled and suggest `/paper-compiler:build-research-context <paper>`.

## Procedure

1. **Read `research/research.md` first.** Always. Before any planning. Before any code.
2. **For each major implementation decision**, query the paper-compiler MCP tools:
   - Architecture component? → `trace_dependency("architecture")`.
   - Loss function? → `trace_dependency("loss")`.
   - Dataset / preprocessing? → `trace_dependency("dataset")` / `trace_dependency("preprocessing")`.
   - Evaluation protocol? → `trace_dependency("evaluation")`.
   - Baseline? → `trace_dependency("baseline")`.
   - Specific question? → `find_atom(<keyword>)` then `get_evidence(<atom-id>)`.
3. **Before adopting any detail not stated in the paper**, check `list_missing_details()`. If the detail is listed there, the paper + neighborhood do not determine it. Treat it as an explicit assumption.
4. **Cite evidence in code comments** for non-obvious choices, in the form: `# per research/evidence/<atom-id>.md`.

## Rules

- **Do not** rely on model memory for paper-specific implementation details when the brief is available. Prefer the brief and the MCP tools.
- **Do not** rephrase the brief into a long plan. Read it, query specifics, then write code.
- If the brief disagrees with the paper PDF as you read it, trust the brief — it is grounded in the citation neighborhood. Surface the disagreement to the user.
- When a detail is genuinely undetermined (in `missing-details.md`), make the assumption visible in the code: name it, comment it, and add it to a TODO list at the end of the response.
- Stay concise. The brief is in context — you don't need to recap it back to the user.
```

### 4.3 `audit-against-research` — auto-invoke during review / completion

**File:** `skills/audit-against-research/SKILL.md`

```markdown
---
name: audit-against-research
description: Use this skill when finishing an implementation, reviewing a PR, or when the user asks to verify that code matches the paper. Cross-checks the repository against research/research.md and the paper-compiler MCP graph, flags missing or divergent components, and produces an audit report.
allowed-tools:
  - Read
  - Grep
  - Glob
  - mcp__paper-compiler__*
---

# Audit implementation against compiled research context

## Trigger

Activate when **any** of the following:

- The user asks to review / audit / verify the implementation against the paper.
- The user has just finished a major implementation milestone (e.g. "I think I'm done").
- A PR is being prepared from work originating in a paper.

## Procedure

1. **Read `research/research.md`** to load the expected implementation atoms.
2. **List required atoms** via `graph_stats()` and the architecture/loss/dataset/eval traces.
3. **For each required atom**, search the repo for evidence of implementation:
   - Use `Grep` / `Glob` to find candidate files.
   - Read the implementing code.
   - Compare against `get_evidence(<atom-id>)`.
4. **Score each atom** as: `IMPLEMENTED`, `PARTIAL`, `MISSING`, `DIVERGENT`.
5. **For each non-IMPLEMENTED atom**, generate a one-line summary of the gap.
6. **Cross-check `list_missing_details()`** — for every open assumption, confirm the code makes a visible choice and that choice is justified.
7. **Produce the audit report.**

## Audit report template

```
Paper: <title>
Atoms expected: <N>
- Implemented: <count>
- Partial:     <count>
- Missing:     <count>
- Divergent:   <count>

Findings:
- [MISSING]   <atom-name>: <one-line gap>
- [DIVERGENT] <atom-name>: <code says X, brief says Y>
- [PARTIAL]   <atom-name>: <what's there, what's not>

Open assumptions still unflagged in code:
- <missing-detail-id>: <one-liner>

Recommended next steps:
1. ...
```

## Rules

- Only flag DIVERGENT when you have evidence from the MCP graph that contradicts the code. Mere stylistic disagreement is not divergence.
- For ambiguous atoms (e.g. "preprocessing"), require the code to make a single, named, commented choice — not "any of these would work."
- Do not auto-fix divergences. Surface them. The user decides.
```

---

## 5. Subagents — `research-explorer`

We use **one** subagent: a forked exploration agent invoked by the `build-research-context` skill via `context: fork`.

In practice, the `build` skill itself is the subagent — we don't need a separate `agents/research-explorer.md` for v1. If you want to expose it as a callable subagent independent of the build skill (e.g. for ad-hoc "explore this citation neighborhood" requests), add:

**File:** `agents/research-explorer.md`

```markdown
---
name: research-explorer
description: A forked agent that explores a paper's citation neighborhood and produces a structured exploration report. Use when the user wants to investigate a paper before deciding whether to compile it, or when a question about an already-compiled paper requires reaching deeper than the existing graph.
---

You are an exploration agent. You have access to the paper-compiler CLI and MCP tools but you do not write to the user's repo. Your job is to investigate and report.

[... operating procedure ...]
```

For v1, ship without the standalone subagent and add it in v1.5 if there's demand.

---

## 6. MCP server — `.mcp.json` and the server itself

### 6.1 The declaration

**File:** `.mcp.json` (at the plugin root)

```json
{
  "mcpServers": {
    "paper-compiler": {
      "command": "python",
      "args": [
        "-m",
        "paper_compiler_mcp.server"
      ],
      "env": {
        "PYTHONPATH": "${CLAUDE_PLUGIN_ROOT}/server/src",
        "PAPER_COMPILER_RESEARCH_DIR": "${PWD}/research"
      }
    }
  }
}
```

Notes:

- `${CLAUDE_PLUGIN_ROOT}` resolves to the plugin's installation root. **Always use it; never hardcode paths.**
- `${PWD}` resolves to the working directory at the time Claude Code starts. This is how the MCP server knows which `research/` directory to read.
- The server reads compiled artifacts; it does not write.

### 6.2 The server implementation

Use the `mcp` Python package (or `@modelcontextprotocol/sdk` for TypeScript — pick one). Below is the Python sketch.

**File:** `server/src/paper_compiler_mcp/server.py`

```python
import os
from pathlib import Path
from mcp.server.fastmcp import FastMCP
from .graph import ResearchGraph

RESEARCH_DIR = Path(os.environ.get("PAPER_COMPILER_RESEARCH_DIR", "./research"))

mcp = FastMCP("paper-compiler")
graph = ResearchGraph.load(RESEARCH_DIR)


@mcp.tool()
def paper_summary(paper_id: str) -> dict:
    """Return metadata and a list of implementation atoms defined or used by this paper."""
    return graph.paper_summary(paper_id)


@mcp.tool()
def trace_dependency(component: str) -> dict:
    """
    Trace the dependency chain for an implementation component.

    component: one of "architecture", "loss", "dataset", "preprocessing",
               "evaluation", "baseline", "optimizer".

    Returns the ordered chain of papers + atoms + evidence span IDs.
    """
    return graph.trace(component)


@mcp.tool()
def find_atom(query: str, limit: int = 5) -> list[dict]:
    """Semantic + BM25 search across implementation atoms."""
    return graph.search_atoms(query, limit=limit)


@mcp.tool()
def get_evidence(atom_id: str) -> list[dict]:
    """Return all evidence spans backing an atom, each with source paper, section, page/equation refs, and verbatim text."""
    return graph.evidence_for(atom_id)


@mcp.tool()
def list_missing_details() -> list[dict]:
    """Return the list of unresolved implementation questions."""
    return graph.missing_details()


@mcp.tool()
def equation_lookup(symbol_or_keyword: str) -> list[dict]:
    """Find equations across the compiled corpus that match a symbol or keyword."""
    return graph.find_equation(symbol_or_keyword)


@mcp.tool()
def compare_methods(atom_a: str, atom_b: str) -> dict:
    """Side-by-side evidence comparison of two implementation atoms."""
    return graph.compare(atom_a, atom_b)


@mcp.tool()
def citation_neighbors(paper_id: str, role: str | None = None) -> list[dict]:
    """Adjacent papers, optionally filtered by citation edge role."""
    return graph.neighbors(paper_id, role=role)


@mcp.tool()
def graph_stats() -> dict:
    """Counts, depth reached, coverage, build manifest, version."""
    return graph.stats()


if __name__ == "__main__":
    mcp.run()
```

### 6.3 Why MCP and not "just read the files"

You could let the `use-research-context` skill read `research/graph.json` directly. Don't. Three reasons:

1. **The graph is too big to fit in context** if you compile a deep neighborhood. The MCP server keeps it on disk and returns only what's asked for.
2. **Structured retrieval > text retrieval** for implementation decisions. The agent should ask "trace the loss dependency", not grep for the word "loss".
3. **Tool calls are auditable.** You can log them, evaluate them, and use them as part of the A/B in §10.2 of the PRD.

---

## 7. Hooks — optional guardrails

For v1, ship **one optional hook** that warns (does not block) when Claude is about to write code that touches an atom listed in `missing-details.md` without the user having acknowledged the assumption.

**File:** `hooks/hooks.json`

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/scripts/check-assumptions.sh"
          }
        ]
      }
    ]
  }
}
```

The script reads `research/missing-details.md`, the file being written, and prints a warning if the file mentions a still-unacknowledged assumption. Exit code 0 lets the write proceed; exit code 2 blocks it. For v1, always exit 0 — warn only.

---

## 8. `CLAUDE.md` — system-instruction layer

`CLAUDE.md` at the plugin root sets house rules that activate when the plugin is enabled. Keep it short.

```markdown
# paper-compiler conventions

This plugin compiles a research paper and its citation neighborhood into an implementation-ready memory.

## When working in a repo with a research/ directory

- Always read research/research.md before planning or coding.
- Never paraphrase the brief back to the user — it's already in context.
- Prefer mcp__paper-compiler__* tool calls to model memory for paper-specific details.
- Cite evidence in code comments using `# per research/evidence/<atom-id>.md` for non-obvious choices.

## When asked to compile a paper

- Use /paper-compiler:build-research-context <id-or-url>.
- Do not invoke the compile from auto-discovery — it's expensive and forks a subagent. Wait for the user.

## When auditing

- Use /paper-compiler:audit-against-research.
- Surface gaps; never auto-fix.
```

---

## 9. Distribution — marketplace.json

For local development:

```bash
claude --plugin-dir ./paper-compiler
```

For sharing via a marketplace, add **`.claude-plugin/marketplace.json`** alongside `plugin.json`:

```json
{
  "name": "paper-compiler-marketplace",
  "version": "0.1.0",
  "plugins": [
    {
      "name": "paper-compiler",
      "source": ".",
      "description": "Compile a research paper into an implementation-ready memory for Claude Code."
    }
  ]
}
```

Users install via:

```bash
/plugin install paper-compiler@your-org/paper-compiler
```

(Exact install command varies; check the marketplace docs at install time.)

---

## 10. A 30-minute scaffold checklist

The first time you do this, do it in this order and don't deviate.

- [ ] `mkdir paper-compiler && cd paper-compiler`
- [ ] `mkdir -p .claude-plugin skills/build-research-context skills/use-research-context skills/audit-against-research scripts cli server hooks`
- [ ] Write `.claude-plugin/plugin.json` (Section 3 above).
- [ ] Write the three `SKILL.md` files. **Stub** the procedures with `echo` commands so you can iterate the wiring before the CLI works.
- [ ] Write `.mcp.json` pointing at a stub MCP server that returns hardcoded responses.
- [ ] Write `CLAUDE.md`.
- [ ] `claude --plugin-dir .` from a test repo.
- [ ] In the test session: `/paper-compiler:build-research-context arxiv:2310.06825`. Confirm the skill triggers and the stub runs.
- [ ] Confirm `mcp__paper-compiler__graph_stats` appears in the tool list.
- [ ] **Stop. Don't write the real CLI or server until the wiring is confirmed.**

Once that's green, build the CLI in `cli/`, then the server in `server/`, and iterate without touching the plugin shell.

---

## 11. Pitfalls

- **`disable-model-invocation` on `build-research-context` is non-negotiable.** Without it, Claude will sometimes auto-invoke the compile on harmless questions. The compile is expensive and surprising.
- **`context: fork` on the build skill is non-negotiable.** Without it, the compile transcript pollutes the main session.
- **Don't put long content in `SKILL.md` bodies.** Once a skill loads, its body stays in context across turns. Push background to `references/` and have the skill `Read` those files only when needed.
- **Don't expose write-tools to `use-research-context` or `audit-against-research`.** They are read-only. The `allowed-tools` lists are deliberate.
- **`${CLAUDE_PLUGIN_ROOT}` resolves correctly even when the plugin is installed from a marketplace.** Anything that hardcodes paths to the plugin source will silently break for users.
- **Test with a fresh repo.** Bugs hide when your dev repo accumulates artifacts. `claude --plugin-dir` against `/tmp/empty-repo` shakes out path issues.
- **MCP server cold start matters.** Keep it under 2 seconds to load the graph. If the compiled graph is large, load lazily on first tool call rather than at import time.
- **Versioning the brief.** `research/research.md` is committed to the user's repo. Treat the schema as a public contract — bumping it is a breaking change for users.

---

## 12. What we are NOT going to do (yet)

- A custom slash command for every MCP tool. The MCP tools are discoverable; the slash commands would clutter the UI.
- A web UI for the graph. The MCP surface is sufficient. A visualization is v2.
- A hook that blocks commits by default. Warn-only in v1; opt-in to block.
- Distributing the MCP server as a standalone (non-plugin) package. v1 ships only inside the plugin.
- Hosting a shared compiled-brief cache. v1 is local-only.

Anything in this list that you find yourself wanting to add — write it down as a v2 candidate, don't sneak it into v1.
