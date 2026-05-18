# Rubric schema

One JSON file per paper at `eval/rubric/<slug>.json`. Shape:

```json
{
  "paper_id": "s2:...",
  "slug": "clip",
  "arxiv": "2103.00020",
  "title": "Learning Transferable Visual Models From Natural Language Supervision",
  "categories": {
    "architecture": [
      {
        "id": "arch-001",
        "description": "Vision encoder is a ViT-B/32 or ResNet-50.",
        "check_type": "auto",
        "check": {
          "type": "import_or_class",
          "patterns": ["ViT", "VisionTransformer", "ResNet50"]
        },
        "weight": 1.0
      }
    ],
    "loss": [
      {
        "id": "loss-001",
        "description": "Symmetric InfoNCE / contrastive cross-entropy across image-text pairs.",
        "check_type": "llm",
        "check": {
          "prompt": "Does the repo implement a symmetric contrastive cross-entropy loss over image-text similarity?"
        },
        "weight": 1.0
      }
    ],
    "dataset": [],
    "preprocessing": [],
    "optimizer": [],
    "evaluation": [],
    "baseline": []
  }
}
```

## check_type

- `auto` — runs `grader/auto.py` checks. Allowed `type`s:
  - `import_or_class` — grep for any of `patterns` in `**/*.py`.
  - `config_value` — load a config file at `path` and assert `key=value`.
  - `function_signature` — find a function and check its arg names.
  - `file_present` — assert at least one path matching `glob` exists.
- `llm` — Sonnet 4.6 grader applies the prompt to a snapshot of the repo.

## Grading

Each leaf yields `pass` / `partial` / `fail` / `not_attempted`. Score:

```
replication_score = (pass + 0.5 * partial) / total
```

Stratified random 10% of leaves get a human grade so we can compute Cohen's kappa against the auto/LLM graders.
