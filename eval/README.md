# Evaluation harness — `paper-compiler`

Per `docs/05-evaluation-plan.md`. Three conditions × 20 papers × bounded sessions = 60 runs.

## Layout

```
eval/
├── README.md                 ← you are here
├── protocol.py               driver: builds fresh repo, installs plugin (B/C),
│                             compiles paper, launches a Claude Code session
│                             with bounded budget, captures transcript + repo.
├── conditions.py             A / B / C condition definitions.
├── rubric/
│   ├── schema.md             rubric format spec
│   └── <paper-slug>.json     per-paper leaf-task rubric
├── grader/
│   ├── auto.py               programmatic checks
│   ├── llm.py                Claude Sonnet 4.6 semantic grader
│   └── human.py              CLI for the 10% audit sample
├── analysis.py               bootstrap CIs, deltas, atom coverage,
│                             hallucination rate, Cohen's kappa
├── papers.csv                the 20-paper sample (frozen)
├── results.csv               grader output, one row per (paper, condition, task)
└── failure-log.md            annotated failures
```

## Workflow

```bash
# 1. freeze the sample
edit eval/papers.csv          # 20 rows: paper_id, arxiv_or_doi, slug

# 2. write/import rubrics
python -m eval.rubric.import_paperbench    # if PaperBench rubric is accessible
# else handcraft eval/rubric/<slug>.json per eval/rubric/schema.md

# 3. run the 60-run study
python -m eval.protocol --condition A --paper-csv eval/papers.csv --out runs/
python -m eval.protocol --condition B --paper-csv eval/papers.csv --out runs/
python -m eval.protocol --condition C --paper-csv eval/papers.csv --out runs/

# 4. grade
python -m eval.grader.auto --runs runs/ --rubric eval/rubric/ --out grades.csv
python -m eval.grader.llm  --runs runs/ --rubric eval/rubric/ --merge grades.csv
python -m eval.grader.human --grades grades.csv --sample 0.10

# 5. analyze
python -m eval.analysis --grades grades.csv --out eval/results.csv
```

## Preconditions before running (eval §12)

1. plugin compiles its own originating papers without manual intervention,
2. dev-set atom coverage ≥ 70%,
3. classifier accuracy ≥ 75% per implementation-critical role.

## Ship gate (eval §8)

- Δ (C – A) ≥ +10 pp on mean replication score.
- Δ (C – B) ≥ +3 pp.
- Hallucination rate in C ≤ 50% of A.
- Atom coverage in C ≥ 1.5× A.
- Compile coverage ≥ 80% on average.
- Grader-human agreement ≥ 0.7 on the audited sample.
