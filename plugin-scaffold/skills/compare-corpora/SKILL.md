---
name: compare-corpora
description: Compare two compiled `research/` artifacts. Use when the user says "compare paper A with paper B", "how does paper X's method differ from paper Y's", or wants a meta-analysis across two papers they've already compiled. Emits `comparison-report.md` with cross-paper atom alignment, conflicting `contradicts` edges, and missing atoms in either side.
disable-model-invocation: true
context: fork
agent: general-purpose
allowed-tools:
  - Bash
  - Read
  - Write
  - mcp__paper-compiler__bind_research_dir
  - mcp__paper-compiler__get_paper_context
  - mcp__paper-compiler__graph_stats
  - mcp__paper-compiler__trace_dependency
  - mcp__paper-compiler__find_atom
  - mcp__paper-compiler__list_communities
  - mcp__paper-compiler__community_summary
---

# compare-corpora — diff two compiled papers

Manual-only. The MCP server serves one corpus at a time; this skill flips the bound research dir between calls via `bind_research_dir`. Output is a single `comparison-report.md` in the user's cwd.

## Inputs

`$ARGUMENTS` is two `--research-dir` paths separated by space (or two repo roots; the skill walks for `research/` if given a repo root):

```
/paper-compiler:compare-corpora /path/to/jepa_impl /path/to/dreamer_impl
```

If only one path is given, ask the user for the second before proceeding.

## Procedure

1. **Validate both artifacts.** For each side:
   - Confirm `<path>/research/build-manifest.json` exists.
   - `bind_research_dir(path="<path>/research")` then `get_paper_context()` → read title, paper_id, atom counts, communities.

2. **Build a side-by-side category map.** Run `trace_dependency(component=<c>)` for each c in `{method, objective, data, procedure, evaluation, baseline, theory}` on both sides; collect atoms by (category, canonical_name).

3. **Align atoms across corpora.** Two atoms are an "aligned pair" if their canonical names (lowercased, punctuation-stripped) match. The compiler's stable `atom_uid` includes the defining paper id, so two papers defining the same concept have *different* uids — alignment is by name + category only.
   - `BOTH` — concept appears in both papers.
   - `A_ONLY` — only in paper A.
   - `B_ONLY` — only in paper B.

4. **Surface contradictions.** For each side, query edges with `best_role='contradicts'` OR `citation_intent='contrasts'` via the MCP server. Highlight any case where paper A contradicts paper B (or vice versa) by checking if the contradicted-edge target paper is the other side's target_paper_id.

5. **Community overlap.** `list_communities()` for both sides; if any community labels are similar (cosine on title? simple lowercase substring match suffices), flag it — the two papers cluster the same neighborhood.

6. **Emit `comparison-report.md`** in the user's cwd (NOT in either research/ artifact, since this is a side-output):

   ```markdown
   # Comparison: <paper-A> vs <paper-B>
   Compiled A: <date>, B: <date>

   ## Summary
   - A: <N_atoms> atoms, <N_communities> communities, <coverage>% coverage
   - B: <N_atoms> atoms, <N_communities> communities, <coverage>% coverage
   - Aligned atoms (BOTH): <count>
   - A-only: <count>; B-only: <count>

   ## Per-category alignment
   ### method
   | BOTH | <atom_a.uid> ↔ <atom_b.uid> | <name> |
   | A_ONLY | <atom_a.uid> | <name> |
   | B_ONLY | <atom_b.uid> | <name> |

   ### objective, data, procedure, evaluation, baseline, theory
   ... (same shape)

   ## Contradictions
   - Paper A's atom `<uid>` (<name>) contradicts paper B's chunk_id=<N> ...
   - (or "_clean — no cross-paper contradictions detected_")

   ## Community overlap
   - A-community-0 (JEPA World Models) overlaps B-community-2 (Latent Predictive Models)
   ```

7. **Append a `compare` event** to both papers' `wiki/log.md`.

## Rules

- **Serial only.** This skill runs one paper at a time; concurrent compare-corpora calls would corrupt the server's bound research dir.
- **No DB writes.** All output lands in the user's cwd. Neither corpus is mutated.
- **Cite uids.** Every atom in the report carries its full `atom_uid` — they're stable, and the user can `get_evidence(atom_uid=...)` from either bound research dir to deep-dive.
