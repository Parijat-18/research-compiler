"""Human grader CLI for the 10% audit sample.

Stratifies the grades CSV by (paper, condition, category), draws a deterministic
random sample, presents each leaf, and records the human verdict alongside the
automated one. Computes Cohen's kappa at the end.
"""

from __future__ import annotations

import argparse
import csv
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

STATUSES = ("pass", "partial", "fail", "not_attempted")


def _kappa(a: list[str], b: list[str]) -> float:
    if not a or len(a) != len(b):
        return 0.0
    n = len(a)
    agree = sum(1 for x, y in zip(a, b) if x == y) / n
    counts_a = Counter(a)
    counts_b = Counter(b)
    chance = sum((counts_a[s] / n) * (counts_b[s] / n) for s in STATUSES)
    if chance >= 1.0:
        return 1.0
    return (agree - chance) / (1.0 - chance)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--grades", required=True)
    p.add_argument("--out", default=None, help="output path; defaults to grades + .human.csv")
    p.add_argument("--sample", type=float, default=0.10)
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    with open(args.grades) as fh:
        rows = list(csv.DictReader(fh))

    strata: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        strata[(r["slug"], r["condition"], r["category"])].append(r)

    rng = random.Random(args.seed)
    sampled: list[dict] = []
    for key, group in strata.items():
        k = max(1, int(round(len(group) * args.sample)))
        sampled.extend(rng.sample(group, k=k))

    sys.stderr.write(f"sampled {len(sampled)} leaves; press q at any prompt to stop\n")
    out_rows: list[dict] = []
    auto_statuses: list[str] = []
    human_statuses: list[str] = []
    for i, r in enumerate(sampled, 1):
        sys.stderr.write(
            f"\n[{i}/{len(sampled)}] {r['slug']}/{r['condition']}/{r['leaf_id']} "
            f"(auto={r['status']})\n  evidence: {r.get('evidence', '')}\n"
        )
        sys.stderr.write(f"  status [pass|partial|fail|not_attempted|q]: ")
        sys.stderr.flush()
        ans = input().strip().lower()
        if ans == "q":
            break
        if ans not in STATUSES:
            ans = "fail"
        out_rows.append({**r, "human_status": ans})
        auto_statuses.append(r["status"])
        human_statuses.append(ans)

    out = args.out or (args.grades + ".human.csv")
    with open(out, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["slug", "condition", "leaf_id", "category", "status", "evidence", "human_status"])
        writer.writeheader()
        for row in out_rows:
            writer.writerow(row)

    kappa = _kappa(auto_statuses, human_statuses)
    print(f"wrote {out}: {len(out_rows)} rows; cohen's kappa={kappa:.3f}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
