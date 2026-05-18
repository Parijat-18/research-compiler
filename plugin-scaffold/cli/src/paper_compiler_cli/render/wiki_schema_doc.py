"""Emit `research/wiki/SCHEMA.md` — contract for the wiki article tree.

This is *not* `research/SCHEMA.md` (which describes the SQLite DB). It tells
Claude what each wiki article type contains and how to write new ones
(`wiki/answers/<slug>.md`) consistently.
"""

from __future__ import annotations

from pathlib import Path

WIKI_SCHEMA_MD = """# Wiki — article schema

This directory is a Karpathy-style llm-wiki: a tree of cross-linked markdown
articles that the compiled DB stays in sync with. Each article type has a
known shape so Claude can read, write, and update them predictably.

## Files

```
wiki/
├── index.md            top-level catalog, regenerated on every compile
├── SCHEMA.md           you are here
├── log.md              append-only event log (compile / ingest / query / lint)
├── atoms/<atom-id>.md  one article per implementation atom
├── papers/paper-<safe-paper-id>.md   one per acquired paper
├── communities/community-<n>.md      one per detected community
└── answers/<slug>.md   promoted Q&A answers (written by wiki-query)
```

## Article types

### `atoms/<atom-id>.md`

```
# <atom name>

- **Category:** `architecture | loss | dataset | preprocessing | evaluation | baseline | optimizer | hyperparameter | training_trick`
- **Atom ID:** `atom-001`
- **Defined by:** [[paper-<safe-id>|Paper title]]
- **Priority:** 0.0–1.0

## Description
…1–3 sentences…

## Evidence
### `ev-NNN` (paper [[paper-…|Title]] · section `sec-…` · method)
> verbatim text

## Related atoms
- [[atom-NNN|Name]] (`category`)

## Query
- `mcp__paper-compiler__get_evidence(atom_id="atom-NNN")`
- `mcp__paper-compiler__find_atom(query="…")`
```

### `papers/paper-<safe-id>.md`

```
# <Paper title>

**Authors:** ..., ..., ...
**Year:** YYYY
**Paper ID:** `s2:<hex>`
**Rank:** 0.0–1.0  ·  Impl. influence: 0.0–N

## Abstract
…

## Atoms defined here
- [[atom-NNN|Name]] (`category`)

## Atoms used by this paper
- [[atom-NNN|Name]] (`category`)

## Cited by
- [[paper-…|Title]] · *role* (conf 0.NN)

## Cites
- [[paper-…|Title]] · *role* (conf 0.NN)

## Query
- `mcp__paper-compiler__paper_summary(paper_id="s2:…")`
- `mcp__paper-compiler__citation_neighbors(paper_id="s2:…")`
```

### `communities/community-<n>.md`

```
# <Community label>  *(community N)*

## Summary
…2–4 sentence LLM-generated summary…

**Size:** P papers · A atoms

## Papers
- [[paper-…|Title]]

## Atoms
- [[atom-NNN|Name]] (`category`)

## Query
- `mcp__paper-compiler__community_summary(community_id=N)`
```

### `answers/<slug>.md` (written by `/paper-compiler:wiki-query`)

A promoted answer page. Must include YAML frontmatter:

```
---
question: "<the original question>"
asked_at: "2026-05-18T02:11Z"
answered_with:
  atoms: ["atom-013", "atom-006"]
  papers: ["s2:530dab…", "s2:5c5e69…"]
  chunks: [46, 1287]
---

# <Slug — the answer's title>

<2–8 paragraphs of synthesized answer, with [[wikilinks]] to every atom and
paper cited. Inline citations use [chunk_id=46] format.>

## Sources
- [[atom-013|CEM optimizer]]
- [[paper-…|The Cross-Entropy Method (Rubinstein 1999)]]
- chunk 46 (paper `s2:530dab…`, section `sec-27`)
```

## `log.md`

Append-only. Top-level H2 per event, ISO-8601 UTC timestamp:

```
## 2026-05-18T02:11Z — compile
- target: s2:530dab…
- papers in neighborhood: 257 (134 acquired)
- atoms: 35
- communities: 5
- wall: 343s
```

Event types: `compile`, `ingest`, `query` (only promoted answers), `lint`.

## Conventions

- All cross-references use `[[id]]` or `[[id|display name]]`. The id matches
  the file basename without `.md` (e.g. `atom-013`, `paper-s2_530dab…`,
  `community-0`).
- Never edit a generated article in place. Re-run `paper-compiler build` or
  `paper-compiler ingest`.
- `answers/` is the only directory Claude writes into during a session.
- Article bodies should reference the underlying DB row by id (`atom_id`,
  `paper_id`, `chunk_id`) so tools can re-fetch the evidence.

## How Claude should use this wiki

- `/paper-compiler:wiki-query <question>` — the canonical entry point.
- Read an atom article (`wiki/atoms/atom-NNN.md`) when you want the focused
  view including evidence + related atoms in one file.
- Read a community article (`wiki/communities/community-N.md`) when you need
  to understand a cluster of related work before reading individual papers.
- Use `index.md` for browsing.
"""


def write_wiki_schema_doc(path: Path) -> None:
    path.write_text(WIKI_SCHEMA_MD)
