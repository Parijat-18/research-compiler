# Wiki `log.md` entry format

The log is append-only. After every answer (promoted or not), append one H2
block to `research/wiki/log.md`.

## Shape

```
## <YYYY-MM-DDTHH:MMZ> — query
- question: "<the user's question, ≤ 100 chars>"
- atoms_cited: [atom-NNN, ...]
- papers_cited: [s2:..., ...]
- chunks_used: [N, ...]
- promoted_to: wiki/answers/<slug>.md  # omit this line if not promoted
```

## Timestamp

UTC, ISO-8601 minute precision. Match the format already in the file.

## Multiple turns in one session

Each turn that produced an answer gets its own log entry. Don't batch.

## Lint hint

If the log grows past 500 lines, `wiki-lint` will offer to roll older
entries into `wiki/log-archive-<year>-<quarter>.md`. No manual rotation
needed.
