#!/usr/bin/env bash
# enforce-mcp-access.sh
#
# PreToolUse hook. Blocks direct Read/Glob/Grep on research/ protected dirs.
# These paths should only be accessed via MCP tools (get_evidence, find_atom,
# query_chunks, etc.). Direct reads bypass the semantic router and reranker.
#
# Exit code 2 → block the tool call and show message to Claude.
# Exit code 0 → allow.

set -euo pipefail

input="$(cat || true)"
if [[ -z "$input" ]]; then
  exit 0
fi

# Extract tool name and path from JSON input.
tool_name=""
file_path=""
if command -v jq >/dev/null 2>&1; then
  tool_name="$(printf '%s' "$input" | jq -r '.tool_name // empty' 2>/dev/null || true)"
  file_path="$(printf '%s' "$input" | jq -r '.tool_input.file_path // .tool_input.path // .tool_input.pattern // empty' 2>/dev/null || true)"
else
  tool_name="$(printf '%s' "$input" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("tool_name") or "")' 2>/dev/null || true)"
  file_path="$(printf '%s' "$input" | python3 -c 'import json,sys; d=json.load(sys.stdin); ti=d.get("tool_input") or {}; print(ti.get("file_path") or ti.get("path") or ti.get("pattern") or "")' 2>/dev/null || true)"
fi

# Only intercept Read, Glob, Grep.
case "$tool_name" in
  Read|Glob|Grep) ;;
  *) exit 0 ;;
esac

if [[ -z "$file_path" ]]; then
  exit 0
fi

# Protected path patterns — MCP tools must be used instead.
protected_patterns=(
  "research/wiki/atoms/"
  "research/wiki/papers/"
  "research/wiki/communities/"
  "research/evidence/"
  "research/graph.json"
  "research/research.db"
  "research/embeddings.npy"
  "research/embeddings.json"
)

for pattern in "${protected_patterns[@]}"; do
  if [[ "$file_path" == *"$pattern"* ]]; then
    printf 'paper-compiler: direct %s on %s is blocked — use MCP tools instead.\n' "$tool_name" "$file_path" >&2
    printf 'paper-compiler: use mcp__paper-compiler__get_evidence / find_atom / query_chunks / paper_text as appropriate.\n' >&2
    printf 'paper-compiler: see research/SCHEMA.md for the full tool surface.\n' >&2
    exit 2
  fi
done

exit 0
