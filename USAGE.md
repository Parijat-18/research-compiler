# USAGE — paper-compiler v2.0

Step-by-step guide for using the plugin on a new repo with a new paper.

Audience: someone who's never used the plugin before, wants to implement a paper from scratch in a fresh repo. The path is the same for ML, physics, chemistry, biology, or any field — the plugin is domain-neutral.

---

## 0. One-time setup (skip if already done)

You only do this once per machine.

### 0.1 Install the CLI + MCP server (editable, picks up future updates)

```bash
cd /Users/parijatch/ml_models/research-compiler

# Base install — covers TeX papers + heuristic classification + BM25 retrieval
pip install -e plugin-scaffold/cli -e plugin-scaffold/server

# Recommended extras for full v2.0 functionality
pip install -e 'plugin-scaffold/cli[indexes,graph]'     # vec search + community graph
pip install -e 'plugin-scaffold/cli[pdf]'               # Docling PDF parser
```

Verify:

```bash
paper-compiler --help          # CLI on PATH
python -c "import paper_compiler_mcp; print('MCP server importable')"
```

### 0.2 Set API keys (`.env` in any consumer repo, OR ~/.zshrc, OR shell env)

```bash
# Strongly recommended (1 RPS dedicated vs anonymous shared pool)
export SEMANTIC_SCHOLAR_API_KEY="..."

# For LLM-based atom extraction + citation classification.
# Pick ONE of these:
#   (a) Run inside a Claude Code session — auto-detects `claude` on PATH, reuses subscription auth via `claude -p`. No key needed.
#   (b) Set ANTHROPIC_API_KEY → uses Anthropic SDK directly.
#   (c) Pass --no-llm to the build command → heuristics only (lower quality).

# Optional: for OpenAlex / Unpaywall / Crossref polite-pool rate limits
export PAPER_COMPILER_CONTACT_EMAIL="you@example.com"
```

### 0.3 (One-time) Confirm Claude Code recognizes the plugin

Open Claude Code in any directory and type:

```
/plugin list
```

If `paper-compiler` is not listed, install via:

```bash
claude --plugin-dir /Users/parijatch/ml_models/research-compiler/plugin-scaffold
```

(or follow the prompts in `/plugin install`.)

---

## 1. Compile a paper into a new repo

The flow: **create empty repo → load plugin → compile paper → research/ is yours**.

### 1.1 Create / cd to your implementation repo

```bash
mkdir -p ~/code/my-paper-impl && cd ~/code/my-paper-impl
git init
```

### 1.2 Open Claude Code with the plugin loaded

```bash
claude --plugin-dir /Users/parijatch/ml_models/research-compiler/plugin-scaffold
```

(Or open `claude` normally if the plugin is registered globally per §0.3.)

### 1.3 Build the research context

In the Claude Code session, type:

```
/paper-compiler:build-research-context arxiv:2210.03629
```

Replace `arxiv:2210.03629` with **your paper**. Accepted forms:

- arXiv ID: `arxiv:2210.03629`, `2210.03629`, or full URL `https://arxiv.org/abs/2210.03629`
- DOI: `10.48550/arXiv.2210.03629` or `doi:10.1038/...`
- Semantic Scholar ID: `s2:<40-hex>`
- Local PDF or TeX tarball path

This forks a subagent that runs the 9-stage pipeline (5–20 min typical). When done, you'll see:

```
research/
├── research.md                 # Human brief (you can read this)
├── CLAUDE-PAPER-CONTEXT.md     # Auto-loaded into every future session
├── build-manifest.json         # Per-rebuild stats
├── research.db                 # sqlite + sqlite-vec + FTS5 (MCP reads this)
├── graph.json                  # Atom graph (MCP reads this)
├── decisions.md                # Empty, ready for gotchas
├── sessions/                   # Empty, populated by Stop hook
├── evidence/                   # Per-atom verbatim spans
└── wiki/                       # Cross-linked markdown wiki
```

**The deny rules in `.claude/settings.json` mean Claude can't read `research/wiki/atoms/*.md`, `research/evidence/*.md`, `research/graph.json`, or `research/research.db` directly.** Every paper-content access goes through the MCP server. You don't have to do anything for this — it's enforced automatically.

### 1.4 Sanity check (optional)

From a terminal in the same repo:

```bash
${CLAUDE_PLUGIN_ROOT:-/Users/parijatch/ml_models/research-compiler/plugin-scaffold}/scripts/validate-build-manifest.sh research/
```

Exit codes: 0 = clean, 1 = soft warnings (low coverage / low atoms / single source — usually OK for short papers), 2 = hard fail (recompile or check failure modes in `plugin-scaffold/skills/build-research-context/SKILL.md`).

---

## 2. Implement the paper

In the same session (or a new one — the SessionStart hook auto-loads context):

```
implement the loss function
```

The UserPromptSubmit hook will detect intent and suggest the right sub-skill. You'll see something like:

```
💡 paper-compiler tip: for objective/loss implementation:
   /paper-compiler:use-research-context implement-objective
```

Run that. The sub-skill forks into a policy-island sub-agent with a tight MCP-tool whitelist and walks the playbook:

1. Trace the dependency
2. Pull verbatim definition from MCP (`get_evidence`, `paper_text`)
3. Resolve math via `equation_lookup`
4. Find parameter values via `query_chunks(prefer_kind="table")`
5. Implement with `# per atom_uid <hex>` citations
6. Record load-bearing choices via `record_decision` (asks before writing)

Each category has a sub-skill:

| User says | Sub-skill invoked |
| --- | --- |
| "implement the encoder / scheme / route" | `implement-method` |
| "implement the loss / objective / yield target / fitness" | `implement-objective` |
| "implement the dataset / preprocessing / data loader" | `implement-data` |
| "implement the training loop / integrator / reaction conditions" | `implement-procedure` |
| "evaluate accuracy / convergence / yield" | `implement-evaluation` |
| "add the baseline" | `implement-baseline` |
| "the loss is diverging / numbers don't match" | `debug-divergence` |

---

## 3. Day-to-day workflow

### 3.1 Come back later — resume where you left off

Open Claude Code in the repo, then:

```
continue
```

The UserPromptSubmit hook will suggest:

```
💡 paper-compiler tip: looks like a resume request — run `/paper-compiler:resume-session`...
```

Run that. You'll get a one-screen summary:

```
📄 Paper: <title>
🕐 Last session: 2026-05-19 — encoder-loss
   Atoms touched: <list>
   Files modified: <list>
   Next steps recorded: <list>

📝 Recent decisions: <count>
❓ Open missing-details: <count>

👉 Suggested next move:
   - /paper-compiler:use-research-context continue   (resume implementation)
   - /paper-compiler:audit-against-research          (audit current state)
   - /paper-compiler:wiki-query "<question>"         (new question on corpus)
   - /paper-compiler:wiki-ingest <id>                (add related paper)
```

### 3.2 Record a decision so future sessions see it

In any session, say:

```
we tried InfoNCE and it failed because of representational collapse — switched to MSE per section 4.2
```

The UserPromptSubmit hook will suggest:

```
💡 paper-compiler tip: to persist this as a decision/gotcha so future sessions see it,
   call `mcp__paper-compiler__record_decision`...
```

Claude will call `record_decision(...)`, which asks for your approval, then appends a structured entry to `research/decisions.md`. The next session sees it via `get_decisions_since`.

### 3.3 Ingest a related paper mid-implementation

You discovered the paper cites a key reference you didn't expect. Add it without re-compiling everything:

```
/paper-compiler:wiki-ingest arxiv:1706.03762
```

This appends to the existing `research/` corpus (1–5 min). After it lands, run:

```
/paper-compiler:wiki-lint
```

to confirm no wikilinks broke.

### 3.4 Audit your reproduction before shipping

```
/paper-compiler:audit-against-research
```

Forks a subagent per atom category (audit-method, audit-objective, audit-data, audit-procedure, audit-evaluation, audit-baseline, audit-theory). Emits `audit-report.md` with per-atom verdicts (`IMPLEMENTED` / `PARTIAL` / `MISSING` / `DIVERGENT`). Warn-only — never auto-fixes.

### 3.5 Compare two compiled papers

If you've compiled two papers (each in its own repo):

```
/paper-compiler:compare-corpora /path/to/repo-A /path/to/repo-B
```

Emits `comparison-report.md` in your cwd with cross-paper atom alignment + community overlap + contradicting edges.

### 3.6 Port your implementation to a sibling repo

You've implemented the paper in repo A; now you want to use the same approach in repo B (different domain / use case). From inside repo A's session:

```
/paper-compiler:use-research-context port --target ~/code/other-repo
```

The skill copies `research/` to the target, rewrites `.mcp.json` so the MCP server resolves there, emits a `port-checklist.md` in the target, and dispatches to the right `implement-*` sub-skill for the first TBD atom.

---

## 4. Concrete walkthrough — a new paper from scratch

Let's say you want to implement **the FlashAttention paper (arxiv:2205.14135)** in a brand new repo.

```bash
# 1. Make the repo
mkdir -p ~/code/flash-attn-impl && cd ~/code/flash-attn-impl
git init

# 2. Set keys (one-time per shell, OR put them in ~/.zshrc)
export SEMANTIC_SCHOLAR_API_KEY="..."
export PAPER_COMPILER_CONTACT_EMAIL="me@example.com"

# 3. Open Claude Code with the plugin
claude --plugin-dir /Users/parijatch/ml_models/research-compiler/plugin-scaffold
```

Inside the Claude Code session:

```
/paper-compiler:build-research-context arxiv:2205.14135
```

Wait ~10 min. Then:

```
implement the tiling forward pass
```

Hook suggests `implement-method`. Sub-skill forks, traces the dependency, pulls the verbatim from MCP (`get_evidence`), reads the equations (`equation_lookup`), writes `src/forward.py` with `# per atom_uid <hex>` citations.

Some hours later:

```
the numbers don't match the paper's table 1
```

Hook suggests `debug-divergence`. Sub-skill checks `get_decisions_since`, re-pulls the chunk for the suspected atom, walks the citation neighborhood. Finds a missed normalization step. Records the resolution via `record_decision`.

Session ends. Stop hook writes `research/sessions/2026-XX-XX-flash-attn-tiling.md`.

Three days later:

```
claude --plugin-dir /Users/parijatch/ml_models/research-compiler/plugin-scaffold
```

In the new session:

```
continue
```

`/paper-compiler:resume-session` is suggested. You see the last session's atoms touched, the missed normalization decision, and the remaining atoms. Pick up exactly where you left off.

---

## 5. Where things live

| Path | Purpose | Editable by hand? |
| --- | --- | --- |
| `research/research.md` | Human-readable brief | No (regenerated each compile) |
| `research/CLAUDE-PAPER-CONTEXT.md` | Auto-loaded session context | No (regenerated each compile) |
| `research/research.db` | Graph RAG store | No (MCP read-only) |
| `research/graph.json` | Atom graph | No (MCP read-only) |
| `research/evidence/` | Per-atom verbatim spans | No (regenerated) |
| `research/wiki/` | Cross-linked articles | No (regenerated) — *except* `wiki/answers/<slug>.md` (survives rebuilds, gets re-indexed) |
| `research/decisions.md` | Append-only structured decisions | **Yes** (or via `record_decision` MCP tool) |
| `research/sessions/<date>-<slug>.md` | Per-session notes | **Yes** (or via Stop hook + `append_session_note`) |
| `~/.cache/paper-compiler/` | Content-addressed cache (S2 metadata, parsed IRs, downloaded papers) | No (delete to force re-fetch) |

---

## 6. Troubleshooting

### `paper-compiler` not on PATH

Ensure the editable install worked. From the research-compiler repo:

```bash
pip install -e plugin-scaffold/cli -e plugin-scaffold/server
which paper-compiler
```

### Plugin not visible in `/plugin list`

```bash
claude --plugin-dir /Users/parijatch/ml_models/research-compiler/plugin-scaffold
```

If it still doesn't appear, check that `plugin-scaffold/.claude-plugin/plugin.json` exists.

### `denyTools` blocks something you actually need

Phase A's deny patterns target `research/wiki/atoms/`, `research/wiki/papers/`, `research/wiki/communities/`, `research/evidence/`, `research/graph.json`, `research/research.db`. They do **not** block:

- `research/research.md`
- `research/CLAUDE-PAPER-CONTEXT.md`
- `research/decisions.md`
- `research/sessions/*.md`
- `research/missing-details.md`
- `research/build-manifest.json`
- `research/SCHEMA.md`

If you really need to bypass (for debugging the artifact itself), edit your *personal* `~/.claude/settings.json` to override.

### `validate-build-manifest.sh` reports soft warnings

- `coverage_pct < 70`: your paper has a small or unusual bibliography. Often fine.
- `atoms_extracted < 30`: short paper, or LLM budget too low. Try `--atom-llm-calls 120`.
- `papers_by_source < 2`: only arxiv resolved. Set `PAPER_COMPILER_CONTACT_EMAIL` so OpenAlex/Unpaywall/Crossref kick in.
- `papers_with_atoms_ratio < 0.6`: neighborhood-wide extraction missed many papers. Often fine for short papers; investigate if the corpus is large.

### Session start hook didn't fire

Check that you're in a directory with a `research/build-manifest.json` (or a subdirectory of one — the hook walks up from cwd). Verify with:

```bash
/Users/parijatch/ml_models/research-compiler/plugin-scaffold/scripts/session-start.sh < /dev/null | head -5
```

### MCP server can't find research/

In sibling-repo / ported-repo cases, the per-repo `.mcp.json` must point at the right `research/`. The port-skill writes it correctly. If you copied `research/` manually, write your own `.mcp.json`:

```json
{
  "mcpServers": {
    "paper-compiler": {
      "command": "python",
      "args": ["-m", "paper_compiler_mcp.server"],
      "env": {
        "PYTHONPATH": "${CLAUDE_PLUGIN_ROOT}/server/src",
        "PAPER_COMPILER_RESEARCH_DIR": "/absolute/path/to/this/repo/research"
      }
    }
  }
}
```

---

## 7. Quick reference

```
/paper-compiler:build-research-context <id>     # Compile a paper (5–20 min, forked)
/paper-compiler:use-research-context            # Implement (auto-picks sub-skill)
/paper-compiler:use-research-context continue   # Resume mid-implementation
/paper-compiler:use-research-context port --target <path>   # Port to other repo
/paper-compiler:audit-against-research          # Audit code vs paper
/paper-compiler:wiki-query "<question>"         # Open question on the corpus
/paper-compiler:wiki-ingest <id>                # Add a related paper
/paper-compiler:wiki-lint                       # Health-check the wiki
/paper-compiler:compare-corpora <dirA> <dirB>   # Cross-paper diff
/paper-compiler:resume-session                  # "What was I doing?"
```

All slash commands list in `/` autocomplete. Skill bodies live in `plugin-scaffold/skills/`; deterministic checks live in `plugin-scaffold/scripts/`.

When in doubt:

```
mcp__paper-compiler__get_paper_context()
```

…tells you what's in the corpus and which sub-skill to invoke next.
