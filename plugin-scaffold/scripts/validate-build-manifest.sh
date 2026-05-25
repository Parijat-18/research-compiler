#!/usr/bin/env bash
# validate-build-manifest.sh
#
# Runs the 6 acceptance invariants the v2.0 build-research-context skill
# previously listed as a markdown checklist for Claude to interpret. Now a
# script: deterministic, exit-code-driven, machine-readable.
#
# Usage:    validate-build-manifest.sh [<research-dir>]
# Default:  ./research (or walk-up via find_research_dir).
#
# Exit codes:
#   0  all invariants pass
#   1  at least one soft fail (coverage low, atoms low, source count low) —
#      compile may still be usable; user should review
#   2  hard fail (manifest missing, evidence chunk_id resolution < 100%) —
#      compile is broken; do not proceed
#
# Output: one PASS/FAIL line per invariant on stderr; final JSON summary
# on stdout (machine-readable for the skill body).

set -euo pipefail

# ---- locate research/ --------------------------------------------------------
if [[ $# -ge 1 && -n "$1" ]]; then
  research_dir="$1"
else
  d="$(pwd)"
  research_dir=""
  while [[ "$d" != "/" && "$d" != "" ]]; do
    if [[ -f "$d/research/build-manifest.json" ]]; then
      research_dir="$d/research"
      break
    fi
    d="$(dirname "$d")"
  done
fi

if [[ -z "$research_dir" || ! -d "$research_dir" ]]; then
  echo "FAIL: no research/ directory found" >&2
  printf '{"ok":false,"reason":"no_research_dir"}\n'
  exit 2
fi

manifest="$research_dir/build-manifest.json"
if [[ ! -f "$manifest" ]]; then
  echo "FAIL: $manifest missing" >&2
  printf '{"ok":false,"reason":"manifest_missing"}\n'
  exit 2
fi

# ---- invariants --------------------------------------------------------------
# Pull every value we need in one jq pass to keep cost minimal.
declare -a fails_soft=()
declare -a fails_hard=()
declare -a passes=()

if ! command -v jq >/dev/null 2>&1; then
  echo "FAIL: jq not installed" >&2
  printf '{"ok":false,"reason":"jq_missing"}\n'
  exit 2
fi

coverage_pct="$(jq -r '.coverage.coverage_pct // 0' "$manifest")"
atoms_extracted="$(jq -r '.counts.atoms_extracted // 0' "$manifest")"
papers_in_nbhd="$(jq -r '.counts.papers_in_neighborhood // 0' "$manifest")"
ev_total="$(jq -r '.evidence_provenance.total // 0' "$manifest")"
ev_resolved="$(jq -r '.evidence_provenance.chunk_id_resolved // 0' "$manifest")"
sources_count="$(jq -r '.papers_by_source | length // 0' "$manifest")"
wiki_answers="$(jq -r '.counts.wiki_answers_indexed // 0' "$manifest" 2>/dev/null || echo 0)"

# 1. coverage_pct ≥ 70 (was 50 in v0.2; multi-source acquisition should reach 70+)
if awk -v v="$coverage_pct" 'BEGIN { exit !(v + 0 >= 70) }'; then
  passes+=("coverage_pct=$coverage_pct (≥70)")
  echo "PASS coverage_pct=$coverage_pct (≥70)" >&2
else
  fails_soft+=("coverage_pct=$coverage_pct (<70)")
  echo "SOFT coverage_pct=$coverage_pct (<70)" >&2
fi

# 2. atoms_extracted ≥ 30 (v0.2 was ≥8; Phase 5 neighborhood-wide extraction should hit 30+)
if [[ "$atoms_extracted" -ge 30 ]]; then
  passes+=("atoms_extracted=$atoms_extracted (≥30)")
  echo "PASS atoms_extracted=$atoms_extracted (≥30)" >&2
else
  fails_soft+=("atoms_extracted=$atoms_extracted (<30)")
  echo "SOFT atoms_extracted=$atoms_extracted (<30)" >&2
fi

# 3. evidence_provenance.resolved_pct == 100% — Phase 1's central bug fix.
# This is HARD: if not 100%, the chunk_id NULL bug is back.
if [[ "$ev_total" -gt 0 ]]; then
  if [[ "$ev_resolved" -eq "$ev_total" ]]; then
    passes+=("evidence_provenance=$ev_resolved/$ev_total (100%)")
    echo "PASS evidence_provenance=$ev_resolved/$ev_total (100%)" >&2
  else
    fails_hard+=("evidence_provenance=$ev_resolved/$ev_total (<100%) — Phase 1 chunk_id bug regressed")
    echo "HARD evidence_provenance=$ev_resolved/$ev_total (<100%) — Phase 1 chunk_id bug regressed" >&2
  fi
else
  fails_soft+=("evidence_provenance.total=0 — no atoms have evidence")
  echo "SOFT evidence_provenance.total=0 — no atoms have evidence" >&2
fi

# 4. ≥ 2 distinct papers_by_source values — Phase 3 multi-source acquisition.
if [[ "$sources_count" -ge 2 ]]; then
  passes+=("papers_by_source=$sources_count distinct sources")
  echo "PASS papers_by_source=$sources_count distinct sources (≥2)" >&2
else
  fails_soft+=("papers_by_source=$sources_count (<2 distinct sources)")
  echo "SOFT papers_by_source=$sources_count (<2 distinct sources)" >&2
fi

# 5. papers_in_neighborhood ≥ 5 (else expansion failed entirely — hard fail).
if [[ "$papers_in_nbhd" -ge 5 ]]; then
  passes+=("papers_in_neighborhood=$papers_in_nbhd (≥5)")
  echo "PASS papers_in_neighborhood=$papers_in_nbhd (≥5)" >&2
else
  fails_hard+=("papers_in_neighborhood=$papers_in_nbhd (<5) — expansion failed")
  echo "HARD papers_in_neighborhood=$papers_in_nbhd (<5) — expansion failed" >&2
fi

# 6. papers-with-atoms ≥ 0.6 × papers_acquired (Phase 5 neighborhood-wide
# extraction acceptance). Computed via DB query if available.
db="$research_dir/research.db"
if [[ -f "$db" ]] && command -v sqlite3 >/dev/null 2>&1; then
  acquired_count="$(sqlite3 "$db" "SELECT COUNT(*) FROM papers WHERE acquired=1;" 2>/dev/null || echo 0)"
  with_atoms="$(sqlite3 "$db" "SELECT COUNT(DISTINCT defined_by_paper_id) FROM atoms WHERE defined_by_paper_id IS NOT NULL;" 2>/dev/null || echo 0)"
  if [[ "$acquired_count" -gt 0 ]]; then
    ratio="$(awk -v a="$with_atoms" -v b="$acquired_count" 'BEGIN { printf "%.2f", a / b }')"
    if awk -v r="$ratio" 'BEGIN { exit !(r + 0 >= 0.6) }'; then
      passes+=("papers_with_atoms_ratio=$ratio ($with_atoms/$acquired_count, ≥0.6)")
      echo "PASS papers_with_atoms_ratio=$ratio ($with_atoms/$acquired_count, ≥0.6)" >&2
    else
      fails_soft+=("papers_with_atoms_ratio=$ratio ($with_atoms/$acquired_count, <0.6)")
      echo "SOFT papers_with_atoms_ratio=$ratio ($with_atoms/$acquired_count, <0.6)" >&2
    fi
  fi
fi

# ---- summary JSON ------------------------------------------------------------
n_pass=${#passes[@]}
n_soft=${#fails_soft[@]}
n_hard=${#fails_hard[@]}

jq -n \
  --arg research_dir "$research_dir" \
  --argjson n_pass "$n_pass" \
  --argjson n_soft "$n_soft" \
  --argjson n_hard "$n_hard" \
  --argjson coverage_pct "$coverage_pct" \
  --argjson atoms_extracted "$atoms_extracted" \
  --argjson papers_in_nbhd "$papers_in_nbhd" \
  --argjson ev_total "$ev_total" \
  --argjson ev_resolved "$ev_resolved" \
  --argjson sources_count "$sources_count" \
  '{
    research_dir: $research_dir,
    ok: ($n_hard == 0),
    soft_warnings: $n_soft,
    hard_fails: $n_hard,
    coverage_pct: $coverage_pct,
    atoms_extracted: $atoms_extracted,
    papers_in_neighborhood: $papers_in_nbhd,
    evidence_provenance: { total: $ev_total, resolved: $ev_resolved },
    distinct_sources: $sources_count
  }'

if [[ "$n_hard" -gt 0 ]]; then
  exit 2
fi
if [[ "$n_soft" -gt 0 ]]; then
  exit 1
fi
exit 0
