# Research Compiler for Claude Code — Starter Bundle

This bundle is everything you need to start building **paper-compiler**, a Claude Code plugin that compiles a research paper and its citation neighborhood into an implementation-ready memory for coding agents.

You came in with a clear hypothesis and a synthesis of the prior work. This bundle turns that into a buildable project: a PRD, a reading map, a plugin guide, a system architecture, an evaluation plan, and a working plugin scaffold you can `claude --plugin-dir` against on day one.

---

## The one-paragraph framing

> AI research papers are compressed implementation artifacts, not engineering specifications. Their missing implementation context is distributed across the citation neighborhood — cited methods, datasets, baselines, equations, evaluation protocols, prior architectures, experimental conventions. **paper-compiler** ingests a target paper, uses Semantic Scholar as a scholarly graph backbone, parses available PDFs/TeX/source locally, recursively expands the citation tree, classifies each citation edge by *implementation role*, builds an implementation atom graph, and emits a `research.md` dossier plus queryable MCP tools that Claude Code uses while writing the repo.

The thesis being tested:

> A Claude Code session given the target paper **plus** a compiled `research.md` and MCP query tools produces more faithful paper reproductions than a Claude Code session given only the target paper.

The evaluation plan operationalizes "more faithful" along correctness, coverage, and hallucination rate, and tells you the bar to clear before shipping.

---

## What's in this bundle

```
research-compiler/
├── README.md                              ← you are here
├── docs/
│   ├── 01-PRD.md                          Product requirements — what we're building and why
│   ├── 02-research-context.md             Prior work, reading order, where we fit
│   ├── 03-claude-code-plugin-guide.md     How to build the plugin (the hands-on doc)
│   ├── 04-architecture.md                 System design and data model
│   └── 05-evaluation-plan.md              A/B protocol for proving the hypothesis
└── plugin-scaffold/                       Working v0.1 plugin (stubs, but loads in Claude Code)
    ├── .claude-plugin/plugin.json
    ├── skills/
    │   ├── build-research-context/SKILL.md
    │   ├── use-research-context/SKILL.md
    │   └── audit-against-research/SKILL.md
    ├── .mcp.json
    ├── server/                            Bundled MCP server (stub)
    ├── cli/                               CLI compiler (stub)
    ├── hooks/                             Warn-only assumption hook
    ├── scripts/
    ├── CLAUDE.md
    └── README.md
```

---

## How to use this bundle

### If you have 30 minutes today

1. Read `docs/01-PRD.md` end-to-end.
2. From the scaffold directory, run `claude --plugin-dir ./plugin-scaffold` in a fresh test repo.
3. Invoke `/paper-compiler:build-research-context arxiv:2310.06825` and confirm the stub runs.
4. List MCP tools — `mcp__paper-compiler__graph_stats` and friends should appear.

You now have a confirmed-working wiring loop. The whole rest of the project is replacing stubs with real implementations behind stable interfaces.

### If you have a week

Follow the day-by-day reading order in `docs/02-research-context.md §6`. By Friday you will have:

- A working mental model of the four research areas you're standing on.
- Hand-labelled 30 citation contexts with the 11-role label set (and learned whether the label set works).
- Read the PaperBench failure modes (your real requirements list).
- Picked a PDF parser by running 2–3 candidates on the same paper.

### If you're ready to build

Follow the milestone plan in `docs/04-architecture.md §11`. The discipline is:

- **M0** is wiring. Don't write the real CLI until the skills and MCP tools appear correctly.
- **M1** is one paper through the parser. Don't expand the neighborhood until one paper round-trips cleanly.
- **M2** is the classifier. Hand-label first, then build. You will save a week.
- **M3** is the real `research.md`. The hardest part is keeping it under the token budget.
- **M4** is the MCP server with real indexes.
- **M5** is polish + the self-compile gate.
- **M6** is the A/B evaluation per `docs/05-evaluation-plan.md`.

Hard rule before M6: the plugin must compile its own originating paper(s) end-to-end without manual intervention. If it can't compile its own grandparents, it isn't ready to compile yours.

---

## The five key decisions baked into this design

These are the design calls the docs assume; if you disagree with any of them, that's the place to push back before writing code.

1. **Plugin, not standalone CLI.** The packaging is the product. A CLI alone would force users to glue the workflow themselves, and we know from PaperBench they don't.
2. **Local parsed text is the source of truth; Semantic Scholar is the resolver.** This keeps us honest about evidence and gives us a path to offline / high-volume use via the Datasets API.
3. **Implementation atoms as first-class graph nodes.** Not papers, not citations alone. This is where most of the contribution lives. Don't compromise it for ease of implementation.
4. **Compile-time vs. query-time separation.** Heavy work happens once in a forked subagent. The MCP server is read-only at runtime. Anything that blurs this boundary is a bug.
5. **Evaluate against a held-out paper set with a PaperBench-style rubric.** The project succeeds or fails as a research claim, not as a polished tool.

---

## Glossary

- **Atom / implementation atom.** A reusable implementation component (an architecture block, a loss formulation, a dataset, a preprocessing step, an evaluation protocol, etc.). The unit our graph is organized around.
- **Citation edge role.** The implementation role of a citation: `architecture_dependency`, `loss_function_dependency`, `dataset_dependency`, etc. (See PRD §12 for the full label set.)
- **Implementation influence.** A score we compute for each paper in the neighborhood based on how much it contributes to a faithful reproduction, distinct from its scholarly citation count.
- **Brief / research.md.** The compact, human-and-agent-readable summary of the compiled context. The index, not the database.
- **Evidence span.** A verbatim quote from a real paper with section and page references, backing one or more atoms.
- **Frontier policy.** The rule for which papers to expand at the next hop during citation-graph expansion. Prevents combinatorial blowup.
- **Compile plane / storage plane / query plane.** The three runtime layers; see `04-architecture.md §1`.

---

## What this bundle deliberately does NOT contain

- Code for the real parser. Picking it is a week-4 decision (`04-architecture.md §12`); doing it earlier in this document would be premature.
- A list of which 20 papers to evaluate on. See `05-evaluation-plan.md §3`; finalize the set after M3, not before.
- A budget / business model. This is a research/dev document, not a launch plan.
- A literature review beyond the four areas in `02-research-context.md`. If you find yourself wanting more, re-read the "things to not read" section.

---

## A short pep talk

The reason this project is worth building is that the failure mode it targets is real, reproducible, and not addressed by anything currently on the shelf. PaperBench gave us a 21% number to beat. Existing paper-to-code systems start from the target PDF and ignore the citation neighborhood — the very place where the missing details actually live. Claude Code's plugin/skill/MCP/subagent primitives are the right shape for compiling and serving that context to a coding agent.

The risk is over-scoping. Resist building the literature-review tool, the citation visualizer, the hosted backend, the multilingual support, the auto-fix-the-divergence button. Build the smallest version of the implementation memory that proves the hypothesis. The evaluation plan will tell you whether to keep going.

Good luck.
