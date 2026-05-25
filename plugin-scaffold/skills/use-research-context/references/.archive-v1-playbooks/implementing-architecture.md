# Playbook — implementing a `method` atom

This playbook covers the algorithmic / structural unit of the paper: the
*how-it-is-built* layer. In ML it's an architecture (encoder, decoder,
attention block). In physics it's a numerical scheme (finite-volume
solver, lattice update rule). In chemistry it's a synthesis route. In
biology it's an experimental protocol's compute pipeline. The MCP query
pattern is the same across all of them — only the vocabulary you'll see
in the verbatim spans changes.

## 1. Locate the atom

```
find_atom(query="<component name from the user>", limit=5)
```

If the user named a class of component (e.g. "the encoder", "the
integrator", "the synthesis route"), use:

```
trace_dependency(component="method")
```

Returns the ranked chain of `method` atoms with their defining paper IDs.

## 2. Pin the defining paper

Read the atom's `defined_by_paper_id`. If it is the target paper, the
atom is novel and you implement against the target. If it is a cited
paper, the atom is reused — implement against the cited paper, not the
target's paraphrase.

## 3. Pull the source-of-truth text

```
get_evidence(atom_id="atom-NNN")
```

Returns the verbatim spans. If the spans don't include the equation,
shape, or recipe you need, expand:

```
paper_text(paper_id="<defining_paper_id>", section_type="method")
```

Pick the relevant paragraph_ids from the section index, then re-call
with `paragraph_ids=[...] full=True` for the verbatim text only of what
you need.

## 4. Check equations and procedural steps

```
equation_lookup(symbol_or_keyword="<lhs symbol or equation reference>")
```

Pin the load-bearing details. In ML these are indexing conventions
(1-based vs 0-based), softmax dimensions, residual ordering. In physics
they're discretization stencils, time-step ordering, boundary
conditions. In chemistry they're stoichiometry and step order. In
biology they're sequence and timing. These are the off-by-ones that show
up in audits.

## 5. Disambiguate via the graph

When two methods share a name (e.g. "ResNet-50" with different stem,
"Heck coupling" vs "Mizoroki-Heck reaction"), fetch siblings:

```
neighborhood_subgraph(node_id="atom-NNN", hops=2)
```

The `via_atoms` field tells you which papers share the same atom; pick
the defining one.

## 6. Implement

- Match exact shapes/quantities from the verbatim spans. Don't infer
  from the paper's diagrams — they are usually under-specified.
- Where the target paper customizes a method (e.g. "we use a slightly
  modified ViT", "we use a leapfrog integrator with adaptive step
  size"), implement the cited base then layer the modification on top.
  Comment each delta with the chunk_id.
- For non-obvious choices, comment:
  `# per atom-uid <hex> — research/wiki/atoms/<uid>.md` (uid survives
  rebuilds; the sequential atom-id reshuffles).

## Watch-out list (cross-domain)

ML methods:
- **Pre-norm vs post-norm.** Original Transformer is post-norm; most
  modern variants are pre-norm. Check the verbatim span, not memory.
- **Dim multipliers.** "Hidden dim 768, MLP ratio 4" means MLP hidden =
  3072, not 768. Verify with `equation_lookup`.
- **Positional encoding.** Sinusoidal vs learned vs rotary vs none.
- **Attention masking.** Causal vs bidirectional vs prefix-LM.
- **Initialization scheme.** Cite the chunk.

Physics / simulation methods:
- **Integrator order.** RK2 vs RK4 vs symplectic; time step convergence
  is sensitive to this.
- **Boundary conditions.** Periodic vs reflecting vs absorbing.
- **Stencil.** Centered vs upwind; affects stability.
- **Units.** Reduced (LJ / natural) vs SI; conversion factors matter.

Chemistry / wet-lab methods:
- **Stoichiometry and order of addition.** Both matter — flag if missing.
- **Solvent / catalyst / temperature.** Often in a parameter atom; cross-
  reference.
- **Workup and purification.** Frequently in the supplementary; check
  with a broader chunk query.

Biology / sequencing protocols:
- **Library prep kit and adapter.** Affects downstream alignment.
- **Read length and pairing.** Affects coverage math.
- **Reference genome version.** Often stated once and assumed.

## Verification checklist

- [ ] `atom_uid` cited in code (preferred over the sequential `atom_id`).
- [ ] Implemented against the *defining* paper, not the target paper's
      paraphrase (unless they're the same).
- [ ] Equations match `equation_lookup` output.
- [ ] Output shapes / quantities pass a dry-run on the expected input.
- [ ] Open assumptions added to TODO list at end of response.
