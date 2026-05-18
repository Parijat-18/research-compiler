"""Replication score, deltas, bootstrap CIs.

Reads the grades CSV and emits a wide results CSV plus a short summary.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path

STATUS_WEIGHT = {"pass": 1.0, "partial": 0.5, "fail": 0.0, "not_attempted": 0.0, "skipped": None}


def _per_paper_scores(rows: list[dict]) -> dict[tuple[str, str], float]:
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        grouped[(r["slug"], r["condition"])].append(r)
    scores: dict[tuple[str, str], float] = {}
    for key, leaves in grouped.items():
        scored = [STATUS_WEIGHT.get(l["status"]) for l in leaves]
        scored = [s for s in scored if s is not None]
        if not scored:
            continue
        scores[key] = sum(scored) / len(scored)
    return scores


def _bootstrap_ci(values: list[float], n_iter: int = 10_000, alpha: float = 0.05, seed: int = 0) -> tuple[float, float]:
    if not values:
        return (0.0, 0.0)
    rng = random.Random(seed)
    means = []
    for _ in range(n_iter):
        sample = [rng.choice(values) for _ in values]
        means.append(sum(sample) / len(sample))
    means.sort()
    lo = means[int(n_iter * alpha / 2)]
    hi = means[int(n_iter * (1 - alpha / 2))]
    return (lo, hi)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--grades", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args()

    with open(args.grades) as fh:
        rows = list(csv.DictReader(fh))

    scores = _per_paper_scores(rows)
    # one row per (slug, condition)
    out_rows = []
    for (slug, cond), s in sorted(scores.items()):
        out_rows.append({"slug": slug, "condition": cond, "replication_score": round(s, 4)})

    with open(args.out, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["slug", "condition", "replication_score"])
        writer.writeheader()
        for row in out_rows:
            writer.writerow(row)

    # aggregate
    by_cond: dict[str, list[float]] = defaultdict(list)
    for (slug, cond), s in scores.items():
        by_cond[cond].append(s)

    summary = {}
    for cond, vals in by_cond.items():
        mean = sum(vals) / len(vals)
        median = statistics.median(vals)
        lo, hi = _bootstrap_ci(vals)
        summary[cond] = {"n": len(vals), "mean": round(mean, 4), "median": round(median, 4), "ci95": [round(lo, 4), round(hi, 4)]}

    if "A" in summary and "C" in summary:
        summary["delta_C_minus_A"] = round(summary["C"]["mean"] - summary["A"]["mean"], 4)
    if "B" in summary and "C" in summary:
        summary["delta_C_minus_B"] = round(summary["C"]["mean"] - summary["B"]["mean"], 4)

    sys.stdout.write(json.dumps(summary, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
