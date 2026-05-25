#!/usr/bin/env bash
# detect-intent.sh
#
# UserPromptSubmit hook. Reads the user's prompt from the JSON stdin payload
# and matches against intent classes via cheap regex. Emits a one-line hint
# on stdout that Claude Code appends to the user prompt as a soft suggestion.
# Claude is free to override.
#
# Domain-neutral (the plugin compiles ML, physics, chemistry, biology papers).
# Patterns match broad scientific verbs rather than ML jargon.
#
# Note on regex flavor: macOS bash 3.2's [[ =~ ]] is POSIX ERE — no \b word
# boundaries, no \w shortcuts. We rely on space/punctuation boundaries via
# [[:space:]] or [^a-z], and use . instead of '? for optional apostrophes.

set -euo pipefail

input="$(cat || true)"
if [[ -z "$input" ]]; then
  exit 0
fi

prompt=""
if command -v jq >/dev/null 2>&1; then
  prompt="$(printf '%s' "$input" | jq -r '.prompt // empty' 2>/dev/null || true)"
fi
if [[ -z "$prompt" ]]; then
  prompt="$(printf '%s' "$input" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("prompt") or "")' 2>/dev/null || true)"
fi
if [[ -z "$prompt" ]]; then
  exit 0
fi

# Only fire if research/ is in scope (walk up).
research_present=0
d="$(pwd)"
while [[ "$d" != "/" && "$d" != "" ]]; do
  if [[ -f "$d/research/build-manifest.json" ]]; then
    research_present=1
    break
  fi
  d="$(dirname "$d")"
done
if [[ $research_present -eq 0 ]]; then
  exit 0
fi

# Lowercase once for matching.
p="$(printf '%s' "$prompt" | tr '[:upper:]' '[:lower:]')"

suggest() {
  printf '\n💡 paper-compiler tip: %s\n' "$1"
}

# --- resume / continue ---
# Match keywords at word starts via leading non-letter or BOL.
if [[ "$p" =~ (^|[^a-z])(continue|resume|pick[[:space:]]up|where[[:space:]](was|were|are)[[:space:]]we|last[[:space:]]session|yesterday|three[[:space:]]days[[:space:]]ago) ]]; then
  suggest "looks like a resume request — run \`/paper-compiler:resume-session\` to see what you were working on. Or call \`mcp__paper-compiler__list_sessions()\` directly."
  exit 0
fi

# --- cross-corpus compare ---
if [[ "$p" =~ (compare|differ|differs|versus|[[:space:]]vs[[:space:]]) ]]; then
  if [[ "$p" =~ (arxiv|s2:|doi:|paper[[:space:]][ab]|both[[:space:]]papers|two[[:space:]]papers) ]]; then
    suggest "you're comparing across papers — \`/paper-compiler:compare-corpora\` produces a side-by-side report. For two atoms within ONE paper, use \`mcp__paper-compiler__compare_methods\`."
    exit 0
  fi
fi

# --- port to other repo ---
if [[ "$p" =~ (^|[^a-z])(port|adapt[[:space:]]to|transfer[[:space:]]to)(.|$) ]] \
   || [[ "$p" =~ use[[:space:]].*[[:space:]]in[[:space:]](my|this|another|other)[[:space:]](repo|project|codebase) ]]; then
  suggest "porting between repos — \`/paper-compiler:use-research-context port\` copies the compiled artifact to your target repo and emits a port-checklist.md."
  exit 0
fi

# --- audit / verify ---
if [[ "$p" =~ (^|[^a-z])(audit|verify|review|reproduction)(.|$) ]] \
   || [[ "$p" =~ is[[:space:]](this|my|the).*(faithful|correct|right) ]] \
   || [[ "$p" =~ check.*against.*paper ]]; then
  suggest "for audit / reproduction-verification: \`/paper-compiler:audit-against-research\`. The parent skill dispatches per-category audit sub-skills."
  exit 0
fi

# --- decision capture (tried X, didn't work, gotcha, remember that) ---
# Use . for apostrophe in didn.t / doesn.t since macOS bash chokes on '?.
if [[ "$p" =~ (^|[^a-z])(tried|failed|gotcha)(.|$) ]] \
   || [[ "$p" =~ didn.t[[:space:]]work ]] \
   || [[ "$p" =~ doesn.t[[:space:]]work ]] \
   || [[ "$p" =~ (note|remember)[[:space:]](that|this) ]] \
   || [[ "$p" =~ for[[:space:]]the[[:space:]]record ]]; then
  suggest "to persist this as a decision/gotcha so future sessions see it, call \`mcp__paper-compiler__record_decision\` (writes to \`research/decisions.md\`)."
  exit 0
fi

# --- implementation work — route to the right sub-skill by category ---
implement_intent=0
if [[ "$p" =~ (^|[^a-z])(implement|reproduce|build[[:space:]]the|code[[:space:]]up)(.|$) ]]; then
  implement_intent=1
fi
if [[ "$p" =~ port[[:space:]]the[[:space:]](method|loss|objective|architecture|encoder|decoder|integrator|protocol|reaction|scheme) ]]; then
  implement_intent=1
fi

if [[ $implement_intent -eq 1 ]]; then
  if [[ "$p" =~ (loss|objective|reward|fitness|hamiltonian|action|yield) ]]; then
    suggest "for objective/loss implementation: \`/paper-compiler:use-research-context implement-objective\`."
  elif [[ "$p" =~ (dataset|data[[:space:]]|preprocess|measurement|sample|cohort|reads|tokeniz) ]]; then
    suggest "for data/preprocessing implementation: \`/paper-compiler:use-research-context implement-data\`."
  elif [[ "$p" =~ (optimizer|integrator|scheduler|solver|sampler|protocol|reaction[[:space:]]conditions|training[[:space:]]loop) ]]; then
    suggest "for procedure / training-loop / solver implementation: \`/paper-compiler:use-research-context implement-procedure\`."
  elif [[ "$p" =~ (evaluat|metric|accuracy|f1|convergence[[:space:]]diagnostic|cross.?valid) ]]; then
    suggest "for evaluation implementation: \`/paper-compiler:use-research-context implement-evaluation\`."
  elif [[ "$p" =~ (baseline|prior[[:space:]]method|comparator|reference[[:space:]]method|control) ]]; then
    suggest "for baseline implementation: \`/paper-compiler:use-research-context implement-baseline\`."
  else
    suggest "for implementation work: \`/paper-compiler:use-research-context\` (parent skill picks the right sub-skill by atom category)."
  fi
  exit 0
fi

# --- divergence / debugging ---
# Use stems so "diverging" / "divergence" / "diverged" all match. POSIX ERE
# has no \b, so we rely on stems being long enough to be specific.
if [[ "$p" =~ (diverg|disagre|collaps|explod|nan[[:space:]]|inf[[:space:]]) ]] \
   || [[ "$p" =~ doesn.t[[:space:]]match ]] \
   || [[ "$p" =~ don.t[[:space:]]match ]] \
   || [[ "$p" =~ wrong[[:space:]]answer ]] \
   || [[ "$p" =~ yield[[:space:]]is[[:space:]]wrong ]] \
   || [[ "$p" =~ numbers[[:space:]]don.t[[:space:]]match ]]; then
  suggest "for divergence debugging: \`/paper-compiler:use-research-context debug-divergence\` (compares your code path against the atom's verbatim evidence)."
  exit 0
fi

exit 0
