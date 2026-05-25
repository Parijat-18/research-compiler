#!/usr/bin/env bash
# session-start.sh
#
# SessionStart hook. Fires once when a Claude Code session opens in a directory.
# If a research/ artifact is reachable (walking up from cwd to handle the
# "user is in src/" case), emit a structured context block on stdout that
# Claude Code prepends to the session's initial system prompt. Includes:
#
#   - paper title + id from build-manifest.json
#   - atom counts by category (one-line, from graph_stats SQL)
#   - whether sessions/ has prior entries (link to most recent)
#   - whether decisions.md has entries (count)
#   - the CLAUDE-PAPER-CONTEXT.md fragment if present (Phase F)
#   - a hard rule reminder that direct reads of research/wiki/, research/evidence/,
#     and research/graph.json are denied by policy; use MCP tools instead.
#
# Exit code 0 + stdout content → injected into system prompt.
# Exit code 0 + empty stdout    → silent (no research/ in scope).
# Exit code 2 → blocking error (not used here).
#
# Cost target: <50ms on the JEPA artifact. Pure shell + jq + sqlite3.

set -euo pipefail

# ---- locate research/ — CLAUDE_PROJECT_DIR first, then walk up from cwd -----
find_research_dir() {
  # Prefer the authoritative project root set by Claude Code.
  if [[ -n "${CLAUDE_PROJECT_DIR:-}" ]]; then
    if [[ -f "${CLAUDE_PROJECT_DIR}/research/build-manifest.json" ]]; then
      printf '%s\n' "${CLAUDE_PROJECT_DIR}/research"
      return 0
    fi
    return 1  # CLAUDE_PROJECT_DIR set but no build yet — don't escape the boundary
  fi
  local d
  d="$(pwd)"
  while [[ "$d" != "/" && "$d" != "" ]]; do
    if [[ -d "$d/research" && -f "$d/research/build-manifest.json" ]]; then
      printf '%s\n' "$d/research"
      return 0
    fi
    d="$(dirname "$d")"
  done
  return 1
}

research_dir="$(find_research_dir 2>/dev/null || true)"
if [[ -z "${research_dir:-}" ]]; then
  exit 0
fi

# ---- pull metadata ------------------------------------------------------------
manifest="$research_dir/build-manifest.json"
if [[ ! -f "$manifest" ]]; then
  exit 0
fi

title="unknown"
paper_id="unknown"
n_papers=0
n_atoms=0
n_edges=0
coverage_pct=0
if command -v jq >/dev/null 2>&1; then
  title="$(jq -r '.title // "unknown"' "$manifest" 2>/dev/null || echo unknown)"
  paper_id="$(jq -r '.target_paper_id // "unknown"' "$manifest" 2>/dev/null || echo unknown)"
  n_papers="$(jq -r '.counts.papers_in_neighborhood // 0' "$manifest" 2>/dev/null || echo 0)"
  n_atoms="$(jq -r '.counts.atoms_extracted // 0' "$manifest" 2>/dev/null || echo 0)"
  n_edges="$(jq -r '.counts.edges // 0' "$manifest" 2>/dev/null || echo 0)"
  coverage_pct="$(jq -r '.coverage.coverage_pct // 0' "$manifest" 2>/dev/null || echo 0)"
fi

# ---- atom counts by category (cheap sqlite query) ----------------------------
db="$research_dir/research.db"
cat_breakdown=""
if [[ -f "$db" ]] && command -v sqlite3 >/dev/null 2>&1; then
  cat_breakdown="$(
    sqlite3 -separator ': ' "$db" \
      "SELECT category, COUNT(*) FROM atoms GROUP BY category ORDER BY COUNT(*) DESC;" \
      2>/dev/null | paste -sd ', ' - || true
  )"
fi

# ---- prior sessions ----------------------------------------------------------
sessions_dir="$research_dir/sessions"
session_count=0
latest_session=""
if [[ -d "$sessions_dir" ]]; then
  session_count="$(find "$sessions_dir" -maxdepth 1 -type f -name '*.md' 2>/dev/null | wc -l | tr -d ' ')"
  latest_session="$(ls -t "$sessions_dir"/*.md 2>/dev/null | head -1 | xargs -I{} basename {} .md || true)"
fi

# ---- decisions count ----------------------------------------------------------
decisions_file="$research_dir/decisions.md"
decisions_count=0
if [[ -f "$decisions_file" ]]; then
  decisions_count="$(grep -c '^## ' "$decisions_file" 2>/dev/null || true)"
  decisions_count="${decisions_count:-0}"
fi

# ---- per-paper context fragment (Phase F) ------------------------------------
paper_context_file="$research_dir/CLAUDE-PAPER-CONTEXT.md"

# ---- emit context block to stdout --------------------------------------------
cat <<EOF
<paper-compiler-session-start>

A compiled paper context is in scope:

- **Paper:** ${title}
- **Paper ID:** \`${paper_id}\`
- **Research dir:** \`${research_dir}\`
- **Neighborhood:** ${n_papers} papers, ${n_atoms} atoms, ${n_edges} edges, ${coverage_pct}% coverage
- **Atoms by category:** ${cat_breakdown:-"(no DB found)"}
- **Prior sessions:** ${session_count}$(if [[ -n "$latest_session" ]]; then printf ' (latest: %s)' "$latest_session"; fi)
- **Decisions on record:** ${decisions_count}

**Hard rules in this session (enforced via PreToolUse hook):**
- Direct \`Read\` / \`Glob\` / \`Grep\` on \`research/wiki/atoms/\`, \`research/wiki/papers/\`,
  \`research/wiki/communities/\`, \`research/evidence/\`, \`research/graph.json\`, and
  \`research/research.db\` is **blocked by plugin policy**. Use MCP tools instead — they
  return structured snippets and are autoApproved.
- For ANY question about the paper's atoms / methods / objectives / procedures,
  call \`mcp__paper-compiler__get_paper_context()\` first; it tells you which
  retrieval mode to use.
- For implementation work: \`/paper-compiler:use-research-context\` (the parent
  skill dispatches to a sub-skill by atom category).
- For resume / "where were we": \`/paper-compiler:resume-session\` or
  \`mcp__paper-compiler__list_sessions()\`.

EOF

# Optional: inline the per-paper context fragment if it exists.
if [[ -f "$paper_context_file" ]]; then
  echo
  cat "$paper_context_file"
  echo
fi

echo '</paper-compiler-session-start>'

exit 0
