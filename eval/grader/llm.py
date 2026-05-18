"""LLM grader (Claude Sonnet 4.6, temperature 0).

For leaves with `check_type == "llm"`, sends a structured rubric prompt with a
compact view of the run repo (file tree + selected file contents) and asks for
a strict pass/partial/fail/not_attempted verdict with a one-line rationale.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

SYSTEM = (
    "You grade research-paper reproductions. For one rubric leaf you receive: "
    "the leaf prompt, paper context, and a repo snapshot. Return JSON: "
    "{\"status\":\"pass|partial|fail|not_attempted\",\"rationale\":\"<≤25 words>\"}."
)

MAX_FILES = 30
MAX_FILE_BYTES = 6000


def _snapshot(repo: Path) -> str:
    files = []
    for p in sorted(repo.rglob("*.py")):
        if "/.git/" in str(p) or "/research/" in str(p):
            continue
        files.append(p)
    files = files[:MAX_FILES]
    out = [f"# Repo {repo}"]
    out.append("Files:\n" + "\n".join(str(f.relative_to(repo)) for f in files))
    for f in files[:15]:
        try:
            txt = f.read_text(errors="ignore")[:MAX_FILE_BYTES]
        except OSError:
            continue
        out.append(f"## {f.relative_to(repo)}\n```python\n{txt}\n```")
    return "\n\n".join(out)


def grade_leaf(client, rubric: dict, leaf: dict, repo: Path) -> dict:
    body = (
        f"Paper: {rubric.get('title')}\n"
        f"Category: {leaf.get('category', '?')}\n"
        f"Leaf id: {leaf['id']}\n"
        f"Leaf description: {leaf.get('description', '')}\n"
        f"Grader prompt: {leaf.get('check', {}).get('prompt', '')}\n\n"
        f"---\n{_snapshot(repo)}\n"
    )
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=200,
        temperature=0,
        system=SYSTEM,
        messages=[{"role": "user", "content": body}],
    )
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    s, e = text.find("{"), text.rfind("}")
    if s == -1 or e == -1:
        return {"status": "fail", "rationale": "grader did not return JSON"}
    try:
        data = json.loads(text[s : e + 1])
        return {"status": data.get("status", "fail"), "rationale": (data.get("rationale") or "")[:200]}
    except json.JSONDecodeError:
        return {"status": "fail", "rationale": "json decode failed"}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--runs", required=True)
    p.add_argument("--rubric", required=True)
    p.add_argument("--merge", required=True, help="grades CSV to append to (from auto grader)")
    p.add_argument("--out", default=None)
    args = p.parse_args()

    try:
        from anthropic import Anthropic
    except ImportError:
        print("anthropic SDK required for LLM grader", file=sys.stderr)
        return 2
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ANTHROPIC_API_KEY required", file=sys.stderr)
        return 2
    client = Anthropic(api_key=api_key)

    rubric_dir = Path(args.rubric)
    runs_dir = Path(args.runs)
    out_path = args.out or args.merge
    rows: list[dict] = []
    if Path(args.merge).exists():
        with open(args.merge) as fh:
            rows = list(csv.DictReader(fh))

    for cond_dir in runs_dir.iterdir():
        if not cond_dir.is_dir():
            continue
        condition = cond_dir.name
        for paper_repo in cond_dir.iterdir():
            slug = paper_repo.name
            rubric_path = rubric_dir / f"{slug}.json"
            if not rubric_path.exists():
                continue
            rubric = json.loads(rubric_path.read_text())
            for category, leaves in rubric.get("categories", {}).items():
                for leaf in leaves:
                    if leaf.get("check_type") != "llm":
                        continue
                    res = grade_leaf(client, rubric, {**leaf, "category": category}, paper_repo)
                    rows.append(
                        {
                            "slug": slug,
                            "condition": condition,
                            "leaf_id": leaf["id"],
                            "category": category,
                            "status": res["status"],
                            "evidence": res["rationale"],
                        }
                    )

    with open(out_path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["slug", "condition", "leaf_id", "category", "status", "evidence"])
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    print(f"wrote {out_path}: {len(rows)} rows", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
