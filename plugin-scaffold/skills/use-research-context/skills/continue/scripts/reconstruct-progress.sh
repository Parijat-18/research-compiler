#!/usr/bin/env bash
# reconstruct-progress.sh
#
# Used by the `continue` sub-skill. Walks research/sessions/ + decisions.md
# to reconstruct the state of an in-progress implementation. Emits JSON.
#
# Usage:    reconstruct-progress.sh [<research-dir>]
# Exit:     0 always (caller decides whether reconstruction is meaningful)

set -euo pipefail

# Locate research/ by walk-up.
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
  printf '{"ok":false,"reason":"no_research_dir"}\n'
  exit 0
fi

sessions_dir="$research_dir/sessions"
decisions_file="$research_dir/decisions.md"

# Newest session file.
last_session=""
last_session_date=""
session_count=0
if [[ -d "$sessions_dir" ]]; then
  session_count="$(find "$sessions_dir" -maxdepth 1 -type f -name '*.md' 2>/dev/null | wc -l | tr -d ' ')"
  last_session="$(ls -t "$sessions_dir"/*.md 2>/dev/null | head -1 || true)"
  if [[ -n "$last_session" ]]; then
    # Date is the YYYY-MM-DD prefix on the filename.
    bn="$(basename "$last_session" .md)"
    last_session_date="$(printf '%s' "$bn" | cut -c1-10)"
  fi
fi

# Extract atoms-touched / files-modified from the most recent session note.
atoms_touched_json="[]"
files_modified_json="[]"
if [[ -n "$last_session" && -f "$last_session" ]]; then
  atoms_touched_json="$(
    awk '/^## Atoms touched/,/^## /' "$last_session" \
      | grep -oE '`[^`]+`' \
      | tr -d '`' \
      | jq -R . \
      | jq -s . 2>/dev/null || echo '[]'
  )"
  files_modified_json="$(
    awk '/^## Files modified/,/^## /' "$last_session" \
      | grep -oE '`[^`]+`' \
      | tr -d '`' \
      | jq -R . \
      | jq -s . 2>/dev/null || echo '[]'
  )"
fi

# Recent decisions (entries after the prior-to-most-recent session, if any).
recent_decisions_count=0
if [[ -f "$decisions_file" ]]; then
  # Count H2 entries with a YYYY-MM-DD prefix newer than the second-most-recent session.
  prior_session_date="$(ls -t "$sessions_dir"/*.md 2>/dev/null | sed -n '2p' | xargs -I{} basename {} .md | cut -c1-10 || echo '1970-01-01')"
  recent_decisions_count="$(
    grep -oE '^## [0-9]{4}-[0-9]{2}-[0-9]{2}' "$decisions_file" 2>/dev/null \
      | awk -v cutoff="$prior_session_date" '{ d=substr($0, 4); if (d >= cutoff) c++ } END { print c+0 }'
  )"
fi

# Emit JSON.
jq -n \
  --arg research_dir "$research_dir" \
  --arg last_session "$(basename "${last_session:-}" .md 2>/dev/null || echo '')" \
  --arg last_session_date "$last_session_date" \
  --argjson session_count "$session_count" \
  --argjson atoms_touched "$atoms_touched_json" \
  --argjson files_modified "$files_modified_json" \
  --argjson recent_decisions_count "$recent_decisions_count" \
  '{
    ok: ($session_count > 0),
    research_dir: $research_dir,
    last_session: $last_session,
    last_session_date: $last_session_date,
    total_sessions: $session_count,
    atoms_touched_in_last_session: $atoms_touched,
    files_modified_in_last_session: $files_modified,
    decisions_recorded_since_prior_session: $recent_decisions_count
  }'

exit 0
