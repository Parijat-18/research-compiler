---
name: audit-method
description: Audit `method` atoms (algorithmic/structural units) against the implementation. ML: architecture. Physics: numerical scheme. Chemistry: synthesis route. Biology: protocol.
when_to_use: Auto-invoked by parent audit skill when `method` atoms exist.
context: fork
allowed-tools:
  - Read
  - Grep
  - Glob
  - mcp__paper-compiler__find_atom
  - mcp__paper-compiler__get_evidence
  - mcp__paper-compiler__trace_dependency
  - mcp__paper-compiler__paper_text
---

# audit-method

For each `method` atom in scope, output one verdict line for the parent's `audit-report.md`.

## Recipe

1. `mcp__paper-compiler__trace_dependency(component="method")` — pull the top-25 atoms by priority.

2. For each atom:
   - `Grep` for the atom's name + close synonyms (e.g. ML "ViT encoder" → grep `ViT`, `VisionTransformer`, `encoder`; physics "leapfrog integrator" → grep `leapfrog`, `velocity_verlet`; chem "Heck coupling" → grep `Heck`, `Mizoroki`).
   - Read the matching files.
   - Pull verbatim: `mcp__paper-compiler__get_evidence(atom_id=...)`.
   - Compare:
     - Class / function / pipeline stage exists.
     - Signature accepts the same input quantities mentioned in evidence.
     - Internal structure matches paper depth / order / step count.

3. **Score:**
   - All three match → `IMPLEMENTED`.
   - Structure mismatch (layer count, integrator order, step count) → `DIVERGENT` (cite `chunk_id` + `atom_uid`).
   - Top-level present but sub-component (positional encoding, thermostat, purification step) absent → `PARTIAL`.
   - No grep hit → `MISSING`.

## Output

Append fragments to `audit-report.md` under `### method`. One line per atom:
```
- [<STATUS>] `atom_uid <hex>` — <name> (<file:line> if relevant). <one-line reason if not IMPLEMENTED>
```
