# audit-report.md template

Used by every audit-* sub-skill. Compose into a single `audit-report.md` at the repo root.

```markdown
# Audit — <paper title> (<paper_id>)
Compiled: <compiled_at>
Audited: <YYYY-MM-DDTHH:MMZ>

## Summary
| Status      | Count |
| :---------- | ----: |
| IMPLEMENTED |  ... |
| PARTIAL     |  ... |
| MISSING     |  ... |
| DIVERGENT   |  ... |

## Findings (per category)

### method
- [IMPLEMENTED] `atom_uid <hex>` — name (file: src/encoder.py)
- [PARTIAL]     `atom_uid <hex>` — name (file: src/encoder.py) — missing pre-norm
- [DIVERGENT]   `atom_uid <hex>` — name. Code: <X>. Brief: <Y>. chunk_id=<N>.
- [MISSING]     `atom_uid <hex>` — name. Not found by grep.

### objective
... (mirror)

### data, procedure, evaluation, baseline, theory
... (sections only for categories present in the paper)

## Unflagged assumptions
Every open question in `list_missing_details()` should appear visibly in code.
- md-001: <one-liner> — INVISIBLE in code (need a TODO).

## Recommended next steps
1. ...
2. ...
```

The audit-* sub-skills produce per-category fragments; this skill (the parent) stitches them into one file.
