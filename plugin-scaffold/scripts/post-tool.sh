#!/usr/bin/env bash
# post-tool.sh
#
# PostToolUse hook. Fires after a tool completes. Two roles:
#
# 1. After `mcp__paper-compiler__record_decision` succeeds, append a short
#    line to research/wiki/log.md so the event is visible alongside
#    compile/ingest/lint events.
#
# 2. After `mcp__paper-compiler__append_session_note` or a wiki-ingest
#    Bash run succeeds, suggest a follow-up (lint, audit) via stdout.
#
# Output to stdout is shown to the user (not Claude) as a hint.

set -euo pipefail

input="$(cat || true)"
if [[ -z "$input" ]]; then
  exit 0
fi

tool_name=""
if command -v jq >/dev/null 2>&1; then
  tool_name="$(printf '%s' "$input" | jq -r '.tool_name // empty' 2>/dev/null || true)"
fi
if [[ -z "$tool_name" ]]; then
  tool_name="$(printf '%s' "$input" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("tool_name") or "")' 2>/dev/null || true)"
fi

# Find research/ for log appending (same walk-up logic as session-start).
find_research_dir() {
  local d="$(pwd)"
  while [[ "$d" != "/" && "$d" != "" ]]; do
    if [[ -f "$d/research/build-manifest.json" ]]; then
      printf '%s\n' "$d/research"
      return 0
    fi
    d="$(dirname "$d")"
  done
  return 1
}

research_dir="$(find_research_dir 2>/dev/null || true)"

case "$tool_name" in
  *record_decision*)
    if [[ -n "${research_dir:-}" && -f "$research_dir/wiki/log.md" ]]; then
      printf '\n## %s — decision\n- new decision recorded in `decisions.md`\n' \
        "$(date -u +%Y-%m-%dT%H:%MZ)" >> "$research_dir/wiki/log.md"
    fi
    printf '📝 decision persisted to research/decisions.md\n'
    ;;
  *append_session_note*)
    printf '🧠 session note saved\n'
    ;;
  Bash)
    # Detect wiki-ingest completion by command pattern in input (cheap).
    if [[ "$input" == *"paper-compiler ingest"* ]]; then
      printf '\n💡 corpus grew. Suggested follow-up: `/paper-compiler:wiki-lint` (catches dangling wikilinks, stale atoms).\n'
    fi
    ;;
  *)
    : # silent for everything else
    ;;
esac

exit 0
