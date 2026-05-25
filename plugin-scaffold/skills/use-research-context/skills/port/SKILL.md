---
name: port
description: Port a compiled paper's implementation into a different repo / project. Use when the user says "port this paper's code to <other-repo>", "use this paper's method in <my project>", "adapt this for <use case>". Copies the compiled `research/` artifact, rebinds the MCP server's research dir, and emits a `port-checklist.md` showing per-atom applicability.
when_to_use: User mentions porting, adapting, or applying paper code from one repo to another. Requires a source `research/` and a target repo path.
context: fork
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - mcp__paper-compiler__get_paper_context
  - mcp__paper-compiler__trace_dependency
  - mcp__paper-compiler__find_atom
  - mcp__paper-compiler__get_evidence
  - mcp__paper-compiler__bind_research_dir
  - mcp__paper-compiler__record_decision
---

# port — port a compiled paper into a different repo

The user has a compiled `research/` in repo A and wants to implement (some of) the paper's atoms in repo B. The artifact is git-friendly and portable; this skill copies it cleanly and emits a checklist showing which atoms apply in the target context.

## Procedure

1. **Establish source and target.** From arguments or the user prompt:
   - `<source>` — directory containing the compiled `research/` (or its parent).
   - `<target>` — the destination repo root.

2. **Run the port script:**
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/scripts/adjust-research-dir.sh <source> <target>
   ```
   What it does:
   - Verifies `<source>/research/build-manifest.json` exists.
   - Copies `<source>/research/` → `<target>/research/` (rsync if available, cp -r fallback).
   - Writes/updates `<target>/.mcp.json` so the MCP server resolves to the new location.
   - Initializes `<target>/research/sessions/` if absent.
   - Appends a `port` event to `<target>/research/wiki/log.md`.

3. **Re-bind the MCP server** to the new artifact for this session (so subsequent MCP calls in this skill see the target):
   ```
   mcp__paper-compiler__bind_research_dir(path="<target>/research")
   ```

4. **Get paper context** at the new location:
   ```
   mcp__paper-compiler__get_paper_context()
   ```

5. **Survey target-repo applicability.** For each atom category (`method`, `objective`, `data`, `procedure`, `evaluation`, `baseline`):
   - `mcp__paper-compiler__trace_dependency(component=<category>)` → ranked atoms.
   - Grep the target repo for hints that the atom is already in use, partially used, or out of scope (e.g. a vision repo doesn't need a tokenizer; a chemistry repo doesn't need an integrator).
   - Tag each atom: `APPLIES` / `PARTIAL` / `OUT_OF_SCOPE` / `TBD`.

6. **Emit `<target>/port-checklist.md`** (Write, not Edit, since this is a new artifact):
   ```markdown
   # Port checklist — <paper title> (<paper_id>)
   Source: <source>/research/
   Target: <target>/

   ## method
   - [APPLIES]     `atom_uid <hex>` <name>
   - [TBD]         `atom_uid <hex>` <name> — investigate
   - [OUT_OF_SCOPE] `atom_uid <hex>` <name> — reason

   ## objective, data, procedure, evaluation, baseline
   ... (same shape)
   ```

7. **Record the port decision** so future sessions know this artifact is borrowed:
   ```
   mcp__paper-compiler__record_decision(
     category="method",
     decision="ported research/ from <source> on <date>",
     why="implementing <paper-id> atoms in this repo's context"
   )
   ```

8. **Dispatch to the right `implement-*` sub-skill** for the first TBD atom by priority.

## Rules

- **Never modify the source's `research/`.** This is a one-way copy.
- The target's `research/` becomes the source of truth for this repo; subsequent compiles/ingests of *different* papers in the target should land alongside this one.
- If the target has an existing `research/` for a different paper, **stop and ask** — multi-paper-per-repo is out of scope for v2.0.
