#!/usr/bin/env bash
# setup.sh
#
# SessionStart hook — idempotent first-run setup for a consumer project.
# Runs every session start but exits quickly if already configured.
#
# What it does:
#   1. Finds the project root (CLAUDE_PROJECT_DIR or walk-up from cwd).
#   2. If .claude/settings.json is missing or lacks paper-compiler's
#      enabledPlugins entry, writes a minimal one so the plugin is
#      recognized at project scope.
#   3. Prints a one-line setup notice to stdout (injected into context)
#      only on first run.
#
# Does NOT write research/ or any build artifacts — those are CLI-only.

set -euo pipefail

# Prefer CLAUDE_PROJECT_DIR (set by Claude Code); fall back to cwd walk-up.
find_project_root() {
  local d="${CLAUDE_PROJECT_DIR:-}"
  if [[ -n "$d" && -d "$d" ]]; then
    printf '%s\n' "$d"
    return 0
  fi
  d="$(pwd)"
  while [[ "$d" != "/" && "$d" != "" ]]; do
    if [[ -f "$d/.git/config" || -f "$d/.claude/settings.json" ]]; then
      printf '%s\n' "$d"
      return 0
    fi
    d="$(dirname "$d")"
  done
  # Fall back to cwd.
  printf '%s\n' "$(pwd)"
}

project_root="$(find_project_root)"
settings_file="$project_root/.claude/settings.json"
marker_file="$project_root/.claude/.paper-compiler-setup-done"

# Already configured this project.
if [[ -f "$marker_file" ]]; then
  exit 0
fi

mkdir -p "$project_root/.claude"

# Merge enabledPlugins into settings.json (create if missing, preserve existing).
if [[ ! -f "$settings_file" ]]; then
  printf '{\n  "enabledPlugins": {\n    "paper-compiler@research-compiler-local": true\n  }\n}\n' > "$settings_file"
else
  # Only add if not already present.
  if ! grep -q 'paper-compiler' "$settings_file" 2>/dev/null; then
    if command -v python3 >/dev/null 2>&1; then
      python3 - "$settings_file" <<'PYEOF'
import json, sys
path = sys.argv[1]
with open(path) as f:
    d = json.load(f)
d.setdefault("enabledPlugins", {})["paper-compiler@research-compiler-local"] = True
with open(path, "w") as f:
    json.dump(d, f, indent=2)
    f.write("\n")
PYEOF
    fi
  fi
fi

# Write marker so we don't re-run.
touch "$marker_file"

printf '<paper-compiler-setup>paper-compiler: project configured (.claude/settings.json updated). MCP server will start on next session.</paper-compiler-setup>\n'

exit 0
