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

You are running as a forked subagent. The main Claude Code session will not see your intermediate work — only your final report. Keep your final report tight: paths to generated files, a one-paragraph summary, and any errors.

## Inputs

The user has invoked `/paper-compiler:build-research-context <ID-or-URL>`. The `<ID-or-URL>` is one of:

- An arXiv ID (e.g. `2310.06825`)
- A DOI
- A Semantic Scholar paper ID
- A URL pointing to any of the above
- A local PDF or TeX tarball path

## Procedure

1. **Resolve.** Run `${CLAUDE_PLUGIN_ROOT}/cli/bin/paper-compiler resolve <input>` and read the output to confirm the canonical paper.
2. **Confirm with user if ambiguous.** If `resolve` returned multiple candidates, ask the user which one. Do not proceed on a guess.
3. **Compile.** Run `${CLAUDE_PLUGIN_ROOT}/cli/bin/paper-compiler build <paper-id> --out research/`. This is the long step (5–20 minutes typical).
4. **Read the build manifest.** After `build` exits, read `research/build-manifest.json`. It contains stats, errors, and coverage numbers.
5. **Report back** using the template below.

## Final report template

```
Compiled <paper title>.

Outputs:
- research/research.md
- research/missing-details.md
- research/graph.json
- research/evidence/

Coverage: <N>/<M> references resolved (<pct>%).
Failed acquisitions: <list of paper IDs or "none">
Open implementation questions: <count> — see research/missing-details.md.

Next: review research.md, then ask me to implement.
```

## Rules

- Never run `build` without first running `resolve` and surfacing the canonical paper.
- Never edit `research/` files yourself. The CLI is the only writer.
- If `build` fails, do not retry blindly. Read the error, surface it, ask the user.
- Do not summarize the paper's contents in your report. The summary lives in `research.md`. Your job is to confirm the compile completed.

## TODO (v0.1 scaffold)

The CLI at `${CLAUDE_PLUGIN_ROOT}/cli/bin/paper-compiler` is not implemented yet. For the scaffold phase, this skill should:

1. Confirm the input format.
2. Echo what it *would* run.
3. Write a placeholder `research/research.md` that says "This is a scaffold. Real compile not implemented."

Replace this section once the CLI is real.
