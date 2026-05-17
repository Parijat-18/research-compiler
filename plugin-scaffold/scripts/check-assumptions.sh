#!/usr/bin/env bash
# check-assumptions.sh
#
# PreToolUse hook (warn-only in v0.1). Runs before Write/Edit tool calls.
# Reads research/missing-details.md and warns if the target file mentions any
# still-unacknowledged assumption.
#
# Exit code 0  → allow the tool call.
# Exit code 2  → block the tool call (NOT used in v0.1; warn-only).
#
# Real implementation: parse the tool input JSON from stdin, extract the file path,
# grep it for any missing-detail keyword, and write a warning to stderr.
# For now this is a stub that always allows.

set -euo pipefail

# Read tool input from stdin (Claude Code passes JSON here).
input="$(cat || true)"

# Scaffold: just allow everything. Real logic in v0.2+.
exit 0
