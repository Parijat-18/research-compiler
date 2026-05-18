"""Programmatic rubric grader.

Reads `eval/rubric/<slug>.json` and a run repo, emits one CSV row per leaf:
(slug, condition, category, leaf_id, status, evidence).

Supported leaf check types:
  * import_or_class — grep for any of `patterns` across the repo.
  * config_value    — open `path`, assert key/value pair.
  * function_signature — find `name`, check `args` subset.
  * file_present    — at least one match for `glob`.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Iterable


def _walk_python(repo: Path) -> Iterable[Path]:
    for p in repo.rglob("*.py"):
        if "/.git/" in str(p) or "/research/" in str(p):
            continue
        yield p


def check_import_or_class(repo: Path, check: dict) -> tuple[str, str]:
    patterns = check.get("patterns", [])
    if not patterns:
        return ("fail", "no patterns")
    pat = re.compile("|".join(re.escape(p) for p in patterns))
    for f in _walk_python(repo):
        try:
            txt = f.read_text(errors="ignore")
        except OSError:
            continue
        if pat.search(txt):
            return ("pass", f"match in {f.relative_to(repo)}")
    return ("fail", "not found")


def check_file_present(repo: Path, check: dict) -> tuple[str, str]:
    glob = check.get("glob", "")
    if not glob:
        return ("fail", "no glob")
    matches = list(repo.rglob(glob))
    if matches:
        return ("pass", str(matches[0].relative_to(repo)))
    return ("fail", "no match")


def check_config_value(repo: Path, check: dict) -> tuple[str, str]:
    path = check.get("path")
    key = check.get("key")
    expected = check.get("value")
    if not (path and key):
        return ("fail", "missing path/key")
    p = repo / path
    if not p.exists():
        return ("fail", f"{path} not found")
    txt = p.read_text(errors="ignore")
    m = re.search(rf"{re.escape(key)}\s*[:=]\s*([^\n,#]+)", txt)
    if not m:
        return ("fail", f"{key} not present")
    got = m.group(1).strip().strip(",")
    if expected is None or str(expected) == got:
        return ("pass", f"{key}={got}")
    return ("partial", f"{key}={got} expected {expected}")


def check_function_signature(repo: Path, check: dict) -> tuple[str, str]:
    name = check.get("name")
    required = set(check.get("args") or [])
    if not name:
        return ("fail", "no name")
    pat = re.compile(rf"def\s+{re.escape(name)}\s*\(([^)]*)\)")
    for f in _walk_python(repo):
        try:
            txt = f.read_text(errors="ignore")
        except OSError:
            continue
        m = pat.search(txt)
        if not m:
            continue
        args = {a.strip().split(":")[0].split("=")[0].strip() for a in m.group(1).split(",") if a.strip()}
        if required.issubset(args):
            return ("pass", f"{name}({sorted(args)}) in {f.relative_to(repo)}")
        return ("partial", f"{name} found but missing {sorted(required - args)}")
    return ("fail", f"{name} not found")


DISPATCH = {
    "import_or_class": check_import_or_class,
    "file_present": check_file_present,
    "config_value": check_config_value,
    "function_signature": check_function_signature,
}


def grade_paper(rubric: dict, repo: Path) -> list[dict]:
    rows: list[dict] = []
    for category, leaves in rubric.get("categories", {}).items():
        for leaf in leaves:
            if leaf.get("check_type") != "auto":
                rows.append(
                    {
                        "leaf_id": leaf["id"],
                        "category": category,
                        "status": "skipped",
                        "evidence": "non-auto leaf",
                    }
                )
                continue
            check = leaf.get("check", {})
            fn = DISPATCH.get(check.get("type"))
            if not fn:
                rows.append({"leaf_id": leaf["id"], "category": category, "status": "fail", "evidence": f"unknown type {check.get('type')}"})
                continue
            status, evidence = fn(repo, check)
            rows.append({"leaf_id": leaf["id"], "category": category, "status": status, "evidence": evidence})
    return rows


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--runs", required=True, help="runs/ directory from eval.protocol")
    p.add_argument("--rubric", required=True, help="eval/rubric/ directory")
    p.add_argument("--out", required=True)
    args = p.parse_args()

    runs_dir = Path(args.runs)
    rubric_dir = Path(args.rubric)

    out_rows: list[dict] = []
    for cond_dir in runs_dir.iterdir():
        if not cond_dir.is_dir():
            continue
        condition = cond_dir.name
        for paper_repo in cond_dir.iterdir():
            slug = paper_repo.name
            rubric_path = rubric_dir / f"{slug}.json"
            if not rubric_path.exists():
                print(f"missing rubric {rubric_path}", file=sys.stderr)
                continue
            rubric = json.loads(rubric_path.read_text())
            for r in grade_paper(rubric, paper_repo):
                out_rows.append({"slug": slug, "condition": condition, **r})

    with open(args.out, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["slug", "condition", "leaf_id", "category", "status", "evidence"])
        writer.writeheader()
        for row in out_rows:
            writer.writerow(row)
    print(f"wrote {args.out}: {len(out_rows)} rows", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
