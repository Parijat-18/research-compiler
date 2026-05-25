#!/usr/bin/env bash
# lint-wikilinks.sh
#
# Replaces the wiki-lint skill's procedural markdown with a deterministic
# script. Globs research/wiki/**/*.md, extracts every [[link|...]] target,
# and verifies each one resolves to:
#   - a known atom_uid in the DB (Phase 1 stable IDs; falls back to atom_id
#     for v0.2 artifacts that predate Phase 1)
#   - a paper id (paper-<safe-id>)
#   - a community id (community-N)
#   - another existing wiki page basename (without .md)
#
# Emits a JSON report on stdout for the skill body to render. Stderr has
# human-readable per-finding lines.
#
# Usage:    lint-wikilinks.sh [<research-dir>]
# Exit:     0 if clean, 1 if any broken links / orphans / stale defining
#           papers, 2 on infrastructure failure (no DB, no wiki/).
#
# Bash 3.2 compatible — no `mapfile`, no `declare -A`. Uses sorted files
# and `grep -Fx` to test set membership.

set -euo pipefail

# ---- locate research/ --------------------------------------------------------
if [[ $# -ge 1 && -n "$1" ]]; then
  research_dir="$1"
else
  d="$(pwd)"
  research_dir=""
  while [[ "$d" != "/" && "$d" != "" ]]; do
    if [[ -d "$d/research/wiki" ]]; then
      research_dir="$d/research"
      break
    fi
    d="$(dirname "$d")"
  done
fi

if [[ -z "$research_dir" || ! -d "$research_dir/wiki" ]]; then
  printf '{"ok":false,"reason":"no_wiki_dir"}\n'
  echo "FAIL: research/wiki/ not found" >&2
  exit 2
fi

wiki_dir="$research_dir/wiki"
db="$research_dir/research.db"

if [[ ! -f "$db" ]] || ! command -v sqlite3 >/dev/null 2>&1; then
  printf '{"ok":false,"reason":"no_db"}\n'
  echo "FAIL: research.db missing or sqlite3 not installed" >&2
  exit 2
fi

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

valid_ids_file="$tmp/valid_ids.txt"
broken_file="$tmp/broken.txt"
inbound_file="$tmp/inbound.txt"

# ---- inventory of valid ids -> sorted file -----------------------------------
schema_check="$(sqlite3 "$db" "PRAGMA table_info(atoms);" 2>/dev/null | grep -c '|atom_uid|' || true)"
schema_check="${schema_check:-0}"

# atom ids (uid preferred, falls back to atom_id for v0.2 artifacts).
if [[ "$schema_check" != "0" ]]; then
  sqlite3 "$db" "SELECT atom_uid FROM atoms;" 2>/dev/null >> "$valid_ids_file" || true
else
  sqlite3 "$db" "SELECT atom_id FROM atoms;" 2>/dev/null >> "$valid_ids_file" || true
fi

# paper ids → paper-<safe-id>
sqlite3 "$db" "SELECT paper_id FROM papers;" 2>/dev/null \
  | sed 's/[^A-Za-z0-9_-]/_/g; s/^/paper-/' >> "$valid_ids_file" || true

# community ids → community-N
sqlite3 "$db" "SELECT community_id FROM communities;" 2>/dev/null \
  | sed 's/^/community-/' >> "$valid_ids_file" || true

# Every wiki file basename is also a valid target (allows arbitrary links
# between articles).
find "$wiki_dir" -type f -name '*.md' \
  | xargs -n1 basename \
  | sed 's/\.md$//' >> "$valid_ids_file"

sort -u "$valid_ids_file" -o "$valid_ids_file"

# ---- scan every wiki article for [[targets]] ---------------------------------
> "$broken_file"
> "$inbound_file"

while IFS= read -r f; do
  rel="${f#$wiki_dir/}"
  # Extract [[id|display]] targets. -h drops file: prefix.
  while IFS= read -r target; do
    [[ -z "$target" ]] && continue
    if grep -qFx "$target" "$valid_ids_file"; then
      printf '%s\n' "$target" >> "$inbound_file"
    else
      printf '%s -> %s\n' "$rel" "$target" >> "$broken_file"
    fi
  done < <(
    grep -hoE '\[\[[^]|]+' "$f" 2>/dev/null \
      | sed -E 's/^\[\[//' \
      || true
  )
done < <(find "$wiki_dir" -type f -name '*.md')

# Orphans: every atom-page basename with zero inbound references.
orphan_file="$tmp/orphan.txt"
> "$orphan_file"
inbound_sorted="$tmp/inbound_sorted.txt"
sort -u "$inbound_file" -o "$inbound_sorted" 2>/dev/null || true
if [[ -d "$wiki_dir/atoms" ]]; then
  while IFS= read -r f; do
    bn="$(basename "$f" .md)"
    if ! grep -qFx "$bn" "$inbound_sorted"; then
      printf '%s\n' "$bn" >> "$orphan_file"
    fi
  done < <(find "$wiki_dir/atoms" -type f -name '*.md')
fi

# Stale defining papers: atoms whose defined_by_paper_id no longer exists.
stale_file="$tmp/stale.txt"
sqlite3 -separator ' :: ' "$db" \
  "SELECT a.atom_id, a.defined_by_paper_id FROM atoms a
   LEFT JOIN papers p ON p.paper_id = a.defined_by_paper_id
   WHERE p.paper_id IS NULL;" 2>/dev/null > "$stale_file" || true

n_broken="$(wc -l < "$broken_file" | tr -d ' ')"
n_orphan="$(wc -l < "$orphan_file" | tr -d ' ')"
n_stale="$(wc -l < "$stale_file" | tr -d ' ')"

# ---- human-readable stderr report --------------------------------------------
if [[ "$n_broken" -gt 0 ]]; then
  echo "BROKEN WIKILINKS ($n_broken):" >&2
  head -20 "$broken_file" | sed 's/^/  - /' >&2
  [[ "$n_broken" -gt 20 ]] && echo "  ... (+$((n_broken - 20)) more)" >&2
fi
if [[ "$n_orphan" -gt 0 ]]; then
  echo "ORPHAN ATOM PAGES ($n_orphan):" >&2
  head -10 "$orphan_file" | sed 's/^/  - /' >&2
  [[ "$n_orphan" -gt 10 ]] && echo "  ... (+$((n_orphan - 10)) more)" >&2
fi
if [[ "$n_stale" -gt 0 ]]; then
  echo "STALE DEFINING PAPERS ($n_stale):" >&2
  head -10 "$stale_file" | sed 's/^/  - /' >&2
fi
if [[ "$n_broken" -eq 0 && "$n_orphan" -eq 0 && "$n_stale" -eq 0 ]]; then
  echo "CLEAN: no broken wikilinks, no orphan atoms, no stale defining papers" >&2
fi

# ---- JSON ----------------------------------------------------------------
broken_json="$(jq -R -s -c 'split("\n") | map(select(length > 0))' < "$broken_file")"
orphan_json="$(jq -R -s -c 'split("\n") | map(select(length > 0))' < "$orphan_file")"
stale_json="$( jq -R -s -c 'split("\n") | map(select(length > 0))' < "$stale_file")"

jq -n \
  --arg research_dir "$research_dir" \
  --argjson n_broken "$n_broken" \
  --argjson n_orphan "$n_orphan" \
  --argjson n_stale "$n_stale" \
  --argjson broken "$broken_json" \
  --argjson orphan "$orphan_json" \
  --argjson stale "$stale_json" \
  '{
    research_dir: $research_dir,
    ok: ($n_broken == 0 and $n_orphan == 0 and $n_stale == 0),
    broken_wikilinks: { count: $n_broken, items: $broken },
    orphan_atoms:     { count: $n_orphan, items: $orphan },
    stale_defining:   { count: $n_stale,  items: $stale  }
  }'

if [[ "$n_broken" -gt 0 || "$n_orphan" -gt 0 || "$n_stale" -gt 0 ]]; then
  exit 1
fi
exit 0
