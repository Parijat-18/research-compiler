# paper-compiler conventions

This plugin compiles a research paper and its citation neighborhood into an implementation-ready memory.

## When working in a repo with a `research/` directory

- Always read `research/research.md` before planning or coding.
- Never paraphrase the brief back to the user — it's already in context.
- Prefer `mcp__paper-compiler__*` tool calls to model memory for paper-specific details.
- Cite evidence in code comments using `# per research/evidence/<atom-id>.md` for non-obvious choices.

## When asked to compile a paper

- Use `/paper-compiler:build-research-context <id-or-url>`.
- Do not invoke the compile from auto-discovery — it's expensive and runs in a forked subagent. Wait for the user to ask explicitly.

## When auditing

- Use `/paper-compiler:audit-against-research`.
- Surface gaps; never auto-fix.

## When an MCP tool returns "no evidence"

Treat it as a finding, not a failure. The user wants to know what the brief doesn't cover. Say so and offer to record it in `missing-details.md`.
