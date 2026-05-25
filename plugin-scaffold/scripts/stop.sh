#!/usr/bin/env bash
# stop.sh
#
# Stop hook. Fires once at session end. Writes a structured session note to
# research/sessions/<YYYY-MM-DD>-<slug>.md so the next session (or a
# `/paper-compiler:resume-session` call) can reconstruct what was done.
#
# Cheap: pure shell + jq + best-effort transcript parsing. No LLM call.
# If Claude Code provides a transcript path, we extract atom_uids that were
# referenced, files modified, and any record_decision calls. If not, we
# write a minimal stub the user can flesh out.

set -euo pipefail

input="$(cat || true)"

# Find research/ — CLAUDE_PROJECT_DIR first, then walk-up fallback.
find_research_dir() {
  if [[ -n "${CLAUDE_PROJECT_DIR:-}" ]]; then
    if [[ -f "${CLAUDE_PROJECT_DIR}/research/build-manifest.json" ]]; then
      printf '%s\n' "${CLAUDE_PROJECT_DIR}/research"
      return 0
    fi
    return 1  # CLAUDE_PROJECT_DIR set but no build yet — don't escape the boundary
  fi
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
if [[ -z "${research_dir:-}" ]]; then
  exit 0
fi

sessions_dir="$research_dir/sessions"
mkdir -p "$sessions_dir"

date_iso="$(date -u +%Y-%m-%dT%H:%MZ)"
date_slug="$(date -u +%Y-%m-%d)"
session_id=""
transcript_path=""

if command -v jq >/dev/null 2>&1 && [[ -n "$input" ]]; then
  session_id="$(printf '%s' "$input" | jq -r '.session_id // empty' 2>/dev/null || true)"
  transcript_path="$(printf '%s' "$input" | jq -r '.transcript_path // empty' 2>/dev/null || true)"
fi

# Derive slug from earliest atom_uid touched, or fall back to the session_id.
slug=""
files_touched=()
atoms_touched=()
decisions_made=0

if [[ -n "$transcript_path" && -f "$transcript_path" ]]; then
  # Atoms referenced in tool calls (looks for atom_uid="..."  or atom_id="atom-NNN")
  while IFS= read -r line; do atoms_touched+=("$line"); done < <(
    grep -oE '"atom_u?id"\s*:\s*"[^"]+"' "$transcript_path" 2>/dev/null \
      | sed -E 's/.*"([^"]+)"$/\1/' \
      | sort -u \
      | head -20 || true
  )
  # Files written/edited
  while IFS= read -r line; do files_touched+=("$line"); done < <(
    grep -oE '"file_path"\s*:\s*"[^"]+"' "$transcript_path" 2>/dev/null \
      | sed -E 's/.*"([^"]+)"$/\1/' \
      | sort -u \
      | head -20 || true
  )
  # Count record_decision invocations
  decisions_made="$(grep -c '"tool_name"\s*:\s*"mcp__paper-compiler__record_decision"' "$transcript_path" 2>/dev/null || true)"
  decisions_made="${decisions_made:-0}"
  if [[ ${#atoms_touched[@]} -gt 0 ]]; then
    first="${atoms_touched[0]}"
    slug="${first:0:12}"
  fi
fi

if [[ -z "$slug" ]]; then
  if [[ -n "$session_id" ]]; then
    slug="${session_id:0:8}"
  else
    slug="$(date -u +%H%M%S)"
  fi
fi

# Sanitize slug
slug="$(printf '%s' "$slug" | tr -c 'a-zA-Z0-9-' '-' | sed 's/-\+/-/g; s/^-\|-$//g')"
if [[ -z "$slug" ]]; then
  slug="session"
fi

out="$sessions_dir/${date_slug}-${slug}.md"

# Don't clobber: if a session file already exists for this date+slug, append
# a numeric suffix.
n=1
while [[ -e "$out" ]]; do
  n=$((n + 1))
  out="$sessions_dir/${date_slug}-${slug}-${n}.md"
done

# Pull paper title from manifest (best-effort)
title="unknown"
paper_id=""
if command -v jq >/dev/null 2>&1 && [[ -f "$research_dir/build-manifest.json" ]]; then
  title="$(jq -r '.title // "unknown"' "$research_dir/build-manifest.json" 2>/dev/null || echo unknown)"
  paper_id="$(jq -r '.target_paper_id // ""' "$research_dir/build-manifest.json" 2>/dev/null || echo "")"
fi

{
  printf '# Session %s — %s\n' "$date_slug" "$slug"
  printf '**Ended:** %s\n' "$date_iso"
  printf '**Paper:** %s (`%s`)\n' "$title" "$paper_id"
  if [[ -n "$session_id" ]]; then
    printf '**Session ID:** `%s`\n' "$session_id"
  fi
  printf '\n## Atoms touched\n'
  if [[ ${#atoms_touched[@]} -gt 0 ]]; then
    for a in "${atoms_touched[@]}"; do
      printf -- '- `%s`\n' "$a"
    done
  else
    printf -- '- _(none detected from transcript)_\n'
  fi
  printf '\n## Files modified\n'
  if [[ ${#files_touched[@]} -gt 0 ]]; then
    for f in "${files_touched[@]}"; do
      printf -- '- `%s`\n' "$f"
    done
  else
    printf -- '- _(none detected from transcript)_\n'
  fi
  printf '\n## Decisions recorded\n'
  printf -- '- %s new decisions appended to `decisions.md` this session\n' "$decisions_made"
  printf '\n## Next steps\n'
  printf -- '- _(left for the user to fill in, or re-derive via `mcp__paper-compiler__list_missing_details()`)_\n'
} > "$out"

# Append a one-line event to wiki/log.md (cheap, append-only).
if [[ -f "$research_dir/wiki/log.md" ]]; then
  printf '\n## %s — session-end\n- session: `%s`\n- atoms touched: %d\n- files modified: %d\n- decisions: %d\n' \
    "$date_iso" "$slug" "${#atoms_touched[@]}" "${#files_touched[@]}" "$decisions_made" \
    >> "$research_dir/wiki/log.md"
fi

exit 0
