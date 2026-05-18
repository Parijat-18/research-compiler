# Playbook — implementing an architecture component

When the user asks to implement a model component (encoder, decoder, block,
attention layer, head), follow this exact sequence.

## 1. Locate the atom

```
find_atom(query="<component name from the user>", limit=5)
```

If the user named a class of component ("vision encoder", "MLP head"), use
`trace_dependency(component="architecture")` instead — it returns the ranked
chain with defining paper IDs.

## 2. Pin the defining paper

Read the atom's `defined_by_paper_id`. If it is the target paper, the atom is
novel. If it is a cited paper, the atom is reused — implement against the
cited paper, not the target's paraphrase.

## 3. Pull the source-of-truth text

```
get_evidence(atom_id="atom-NNN")
```

Returns the verbatim spans. If the spans don't include the equation or shape
you need, expand:

```
paper_text(paper_id="<defining_paper_id>", section_type="method")
```

Pick the relevant paragraph_ids from the section index, then re-call with
`paragraph_ids=[...] full=True` for the verbatim text only of what you need.

## 4. Check the equations

```
equation_lookup(symbol_or_keyword="<lhs symbol or eq number>")
```

Pin the indexing convention (1-based vs 0-based), softmax dimension, residual
ordering. These are the off-by-ones that show up in audits.

## 5. Disambiguate via the graph

If two architectures share a name (e.g. "ResNet-50" with different stem),
fetch siblings:

```
neighborhood_subgraph(node_id="atom-NNN", hops=2)
```

The `via_atoms` field tells you which papers share the same atom; pick the
defining one.

## 6. Implement

- Match exact shapes from the verbatim spans. Don't infer from the paper's
  diagrams — they are usually under-specified.
- Where the target paper customizes a component (e.g. "we use a slightly
  modified ViT"), implement the cited base then layer the modification on
  top. Comment each delta with the chunk_id.
- For non-obvious choices, comment: `# per atom-NNN — research/wiki/atoms/atom-NNN.md`.

## Watch-out list

- **Pre-norm vs post-norm.** Original Transformer is post-norm; most modern
  variants are pre-norm. Check the verbatim span, not memory.
- **Dim multipliers.** "Hidden dim 768, MLP ratio 4" means MLP hidden = 3072,
  not 768. Verify with `equation_lookup`.
- **Positional encoding.** Sinusoidal vs learned vs rotary vs none. The paper
  almost always says, but in a one-sentence parenthetical.
- **Attention masking.** Causal vs bidirectional vs prefix-LM. If the
  description is ambiguous, read the experimental setup section.
- **Initialization.** "Truncated normal with std=0.02" is common but never
  universal. Cite the chunk.

## Verification checklist

- [ ] Atom_id cited in code.
- [ ] Implemented against the *defining* paper, not the target paper's
      paraphrase (unless they're the same).
- [ ] Equations match `equation_lookup` output.
- [ ] Shapes pass a dry-forward pass on the expected input.
- [ ] Open assumptions added to TODO list at end of response.
