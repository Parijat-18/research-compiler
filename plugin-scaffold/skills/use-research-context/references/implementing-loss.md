# Playbook — implementing a loss / objective / optimizer

Covers loss functions, training objectives, regularizers, and optimizer
choices (Adam variants, schedules, EMA). Same flow for all of these because
the atoms share a category in the DB.

## 1. Trace the dependency

```
trace_dependency(component="loss")          # or "optimizer"
```

Returns the ordered chain of atoms + their defining papers. The first atom is
usually the one to implement.

## 2. Pull verbatim definition

```
get_evidence(atom_id="atom-NNN")
```

If the verbatim span is short, also pull the surrounding paragraph:

```
paper_text(paper_id="<defining_paper_id>", section_type="method")
```

then `paper_text(..., paragraph_ids=[<the right one>], full=True)`.

## 3. Resolve the math

```
equation_lookup(symbol_or_keyword="<lhs symbol>")
```

Cross-check the indexing convention, sign, normalization, and whether
expectations are over batches or full datasets.

## 4. Hyperparameters

The numbers (temperature, weight, schedule) are usually in *training details*
in the target paper, not the defining paper. Walk:

```
trace_dependency(component="loss")          # → atom-NNN
find_atom(query="<loss name> temperature")  # or "schedule", "warmup"
```

Or, more direct:

```
query_chunks(query="<loss name> temperature schedule")
```

returns snippets pointing to the right chunk. Pull the chunk full-text only
after you've identified the right one.

If `list_missing_details()` includes "temperature schedule for X" or similar,
that's the paper *not* specifying. Choose a reasonable default, comment it,
and add it to the TODO list.

## 5. Implement

- Keep loss code branchless and small — these are the most-audited lines.
- Match reduction (`mean` vs `sum`) and any normalization (per-pixel vs
  per-sample vs per-token).
- For asymmetric losses (e.g. some contrastive setups), implement both
  directions and verify with a synthetic 4-sample test that gives a known
  answer.

## Watch-out list

- **Temperature placement.** `softmax(sim / τ)` not `softmax(sim) / τ`.
- **Negative sign.** Many papers write the loss with a leading minus that
  matters only if you re-derive from log-likelihood — copy the sign from the
  verbatim span verbatim.
- **Padding / mask exclusion.** Sequence losses must exclude padded tokens.
  Almost never spelled out; ask for confirmation in the TODO.
- **Stop-gradient on EMA target.** If the paper says "stop gradient" or
  "target network", that line is load-bearing.
- **Optimizer epsilon.** AdamW eps=1e-8 vs 1e-6 changes mixed-precision
  stability. Check verbatim.

## Verification checklist

- [ ] Atom_id cited in code.
- [ ] Equation matches verbatim span.
- [ ] Hyperparameters from a single named chunk; chunk_id in comment.
- [ ] Synthetic dry-run on 4 hand-built samples returns a sensible loss
      (positive, ~log(N) for randomized labels, etc.).
- [ ] Missing-detail TODO list at end of response.
