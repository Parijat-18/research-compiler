#!/usr/bin/env bash
# check-assumptions.sh
#
# PreToolUse hook for Write/Edit. Warn-only in v0.1.
# Reads research/missing-details.md, extracts keywords from each open question,
# and warns to stderr if the file being written mentions any of those keywords
# without an explicit `# per research/evidence/...` citation.
#
# Exit code 0  → allow.
# Exit code 2  → block (reserved; not used in v0.1).

set -euo pipefail

input="$(cat || true)"
if [[ -z "$input" ]]; then
  exit 0
fi

# Extract file_path from JSON (jq optional; fall back to python).
file_path=""
if command -v jq >/dev/null 2>&1; then
  file_path="$(printf '%s' "$input" | jq -r '.tool_input.file_path // empty' 2>/dev/null || true)"
fi
if [[ -z "$file_path" ]]; then
  file_path="$(printf '%s' "$input" | python3 -c 'import json,sys; d=json.load(sys.stdin); print((d.get("tool_input") or {}).get("file_path") or "")' 2>/dev/null || true)"
fi

if [[ -z "$file_path" || ! -f "$file_path" ]]; then
  exit 0
fi

md_path="research/missing-details.md"
if [[ ! -f "$md_path" ]]; then
  exit 0
fi

# Strip headings + bullet prefixes, pull notable lowercase words ≥5 chars.
mapfile -t keywords < <(
  grep -E '^(##|- |\*\*)' "$md_path" 2>/dev/null \
    | tr '[:upper:]' '[:lower:]' \
    | grep -oE '[a-z][a-z_-]{4,}' \
    | sort -u
)

if [[ ${#keywords[@]} -eq 0 ]]; then
  exit 0
fi

# Skip files that already cite evidence
if grep -qE '#\s*per\s+research/evidence/' "$file_path" 2>/dev/null; then
  exit 0
fi

hits=()
for kw in "${keywords[@]}"; do
  case "$kw" in
    category|question|options|suggested|rationale|implementation|details|paper|none) continue ;;
  esac
  if grep -qiE "\\b${kw}\\b" "$file_path" 2>/dev/null; then
    hits+=("$kw")
  fi
done

if [[ ${#hits[@]} -gt 0 ]]; then
  printf 'paper-compiler: file %s touches unacknowledged assumptions in %s: %s\n' \
    "$file_path" "$md_path" "${hits[*]:0:6}" >&2
  printf 'paper-compiler: cite evidence with "# per research/evidence/<atom-id>.md" or update missing-details.md\n' >&2
fi

exit 0
