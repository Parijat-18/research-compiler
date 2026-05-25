# Playbook — implementation diverges from the paper

When the user says "my numbers don't match", "the model is collapsing",
"the simulation blew up", "the yield is wrong", "this disagrees with
the paper", work through this in order. Domain-neutral; the divergence
signal differs by field but the resolution flow is the same.

## 1. Restate the mismatch precisely

Before any tool call, pin down: which number / behaviour / shape /
trajectory / yield diverges, by how much, and where the user's code
claims to follow the paper.

## 2. Re-pull the source-of-truth chunk

The user's claim "the paper says X" is the first thing to verify. Find
the atom + evidence:

```
find_atom(query="<the component in question>")
get_evidence(atom_id="atom-NNN")
```

Compare verbatim text against the user's belief. Mismatches in this
step are the most common root cause across every domain.

## 3. Compare two components directly

If the user mixed up two:

```
compare_methods(atom_a="atom-NNN", atom_b="atom-MMM")
```

Returns side-by-side evidence + shared papers; tells you immediately
whether they should behave the same or not.

## 4. Walk the graph

Bugs often come from a missing **dependency** atom that the user
didn't realize was load-bearing. Walk the neighborhood of the failing
atom:

```
neighborhood_subgraph(node_id="atom-NNN", hops=2)
```

`via_atoms` highlights cross-paper shared components. If a paper in
the subgraph defines an atom you're not using, that's a candidate fix.

## 5. Walk the citation path

Sometimes the mismatch is in something the paper inherited from a
citation two hops away (e.g. a tokenizer from a 5-year-old paper, a
force-field from a 10-year-old paper):

```
shortest_path(from_id="<target_paper_id>", to_id="<suspect_paper_id>")
```

The returned hops + roles tell you why the suspect paper is related at
all.

## 6. Custom SQL

If the above don't pin it down, fall through to:

```
schema_doc()
graph_sql("...")
```

Useful queries:

- "All edges where the role disagrees between heuristic and llm
  classifiers":
  `SELECT * FROM edges WHERE classifier='llm' AND best_confidence < 0.6`.
- "All atoms used by ≥3 papers" (probably load-bearing):
  `SELECT atom_id, COUNT(*) FROM atom_paper_usage GROUP BY atom_id HAVING COUNT(*) ≥ 3`.
- "All edges that disagree with their cited paper":
  `SELECT * FROM edges WHERE best_role = 'contradicts' OR citation_intent = 'contrasts'`.

## 7. Patch

After finding the divergence:

- Make the smallest change that closes the gap.
- Cite the chunk_id + atom_uid in the patch comment (uid stable across
  rebuilds; sequential id is not).
- Add a one-line entry via `/paper-compiler:wiki-query` if the answer
  was non-obvious — it survives the next compile (Phase 8).

## Watch-out list

- The brief is not the paper. If the brief and the verbatim chunk
  disagree, trust the chunk.
- A failing dry-run on synthetic input often beats reading more code.
  Works equally well for ML (forward pass on 4 samples), physics
  (single-particle test), chemistry (single-step mass balance), and
  biology (one-replicate end-to-end).
- Don't search the web for the paper's text. The corpus *is* the
  canonical source. If something genuinely isn't in the corpus, ingest
  the missing reference with `/paper-compiler:wiki-ingest`.

## Verification checklist

- [ ] Mismatch restated in one sentence.
- [ ] Re-pulled chunk confirms or refutes the user's claim about the
      paper.
- [ ] Fix cites the `atom_uid` + chunk.
- [ ] Synthetic-input dry-run passes.
- [ ] If non-obvious, answer logged via wiki-query.
