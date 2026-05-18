# When to promote an answer to a wiki article

## Promote

Save the answer as `research/wiki/answers/<slug>.md` when **any** is true:

- The answer cites ≥ 2 atoms that live in different communities.
- The answer uses ≥ 3 distinct chunks (`chunk_id`).
- The user asked an explicit "remember this" or "save this" request.
- The question is one a future implementer will likely re-ask (architecture
  comparisons, hyperparameter rationales, dataset provenance).

## Don't promote

- One-off "what does X mean?" questions answered in one paragraph from one
  chunk.
- Questions where the answer is just "see `research.md` section …".
- Requests for code generation — those belong to
  `/paper-compiler:use-research-context`, not the wiki.

## Slug

`<slug>` is kebab-case, ≤ 40 chars, derived from the question. Examples:

- `cem-hyperparameters-by-environment`
- `sigreg-vs-infonce-equivalence`
- `vit-vs-swin-positional-encoding`

If the slug collides with an existing answer, append `-2`, `-3`, ….

## Article shape

Follow `research/wiki/SCHEMA.md::answers/` exactly:

```
---
question: "<the user's question, verbatim>"
asked_at: "<ISO-8601 UTC>"
answered_with:
  atoms: ["atom-NNN", ...]
  papers: ["s2:...", ...]
  chunks: [N, ...]
---

# <Title — short noun phrase>

<2–8 paragraphs of synthesized answer with inline [[wikilinks]] and
parenthetical (chunk_id=N) citations>

## Sources

- [[atom-NNN|name]]
- [[paper-s2_…|title]]
- chunk N (paper `s2:…`, section `sec-…`)
```

## Cross-linking

For each atom you cite, add the new answer's basename to the related
atom's wiki article only if you have explicit Write permission *and* it's
straightforward — otherwise leave it. The next compile re-runs link
maintenance automatically.
