#!/usr/bin/env bash
# select-playbook.sh
#
# Map an atom category (or a free-text user phrase mentioning a category)
# to the right implement-* or debug-* sub-skill path under
# skills/use-research-context/skills/.
#
# Usage:
#   select-playbook.sh <category-or-phrase>
#
# Output (stdout, single line):
#   <category> <sub-skill-name> <slash-command-path>
#
# Exit codes:
#   0 — match found
#   1 — no match (caller should default to the parent skill)
#
# The mapping is domain-neutral and aligned with v1.0 ATOM_CATEGORIES:
#   method        → implement-method
#   objective     → implement-objective
#   data          → implement-data
#   preprocessing → implement-data (shared sub-skill)
#   procedure     → implement-procedure
#   parameter     → implement-procedure (parameters live with procedure)
#   evaluation    → implement-evaluation
#   baseline      → implement-baseline
#   theory        → implement-method (theorems are method-adjacent)
#   debug         → debug-divergence

set -euo pipefail

if [[ $# -lt 1 || -z "$1" ]]; then
  echo "usage: select-playbook.sh <category-or-phrase>" >&2
  exit 1
fi

phrase="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')"

emit() {
  printf '%s %s /paper-compiler:use-research-context %s\n' "$1" "$2" "$2"
}

# Exact category match first (e.g. caller already extracted a category).
case "$phrase" in
  method)        emit method        implement-method;        exit 0 ;;
  objective)     emit objective     implement-objective;     exit 0 ;;
  data)          emit data          implement-data;          exit 0 ;;
  preprocessing) emit preprocessing implement-data;          exit 0 ;;
  procedure)     emit procedure     implement-procedure;     exit 0 ;;
  parameter)     emit parameter     implement-procedure;     exit 0 ;;
  evaluation)    emit evaluation    implement-evaluation;    exit 0 ;;
  baseline)      emit baseline      implement-baseline;      exit 0 ;;
  theory)        emit theory        implement-method;        exit 0 ;;
  debug|debug-divergence|divergence) emit debug debug-divergence; exit 0 ;;
esac

# Free-text routing. Stems are deliberately short so "diverging", "divergence",
# etc. all match without word boundaries (POSIX ERE).
#
# Order matters: check divergence/debug BEFORE the implement-category branches,
# because phrases like "the loss is diverging" mention a category but the user
# really wants debug-divergence, not implement-objective.
if [[ "$phrase" =~ (diverg|disagre|collaps|explod|don.t[[:space:]]match|doesn.t[[:space:]]match) ]]; then
  emit debug debug-divergence
  exit 0
fi
if [[ "$phrase" =~ (loss|objective|reward|fitness|hamiltonian|action|yield|cost[[:space:]]function) ]]; then
  emit objective implement-objective
  exit 0
fi
if [[ "$phrase" =~ (dataset|corpus|preprocess|tokeniz|measurement|sample|cohort|reads|specimen) ]]; then
  emit data implement-data
  exit 0
fi
if [[ "$phrase" =~ (optimizer|integrator|scheduler|solver|sampler|protocol|reaction[[:space:]]conditions|training[[:space:]]loop|step[[:space:]]size|time[[:space:]]step) ]]; then
  emit procedure implement-procedure
  exit 0
fi
if [[ "$phrase" =~ (evaluat|metric|accuracy|f1|convergence[[:space:]]diagnostic|cross.?valid|spectra|chromatograph) ]]; then
  emit evaluation implement-evaluation
  exit 0
fi
if [[ "$phrase" =~ (baseline|prior[[:space:]]method|comparator|reference[[:space:]]method|control[[:space:]]reaction) ]]; then
  emit baseline implement-baseline
  exit 0
fi
if [[ "$phrase" =~ (architecture|encoder|decoder|attention|scheme|algorithm|synthesis|protocol|module|layer|backbone) ]]; then
  emit method implement-method
  exit 0
fi
if [[ "$phrase" =~ (theorem|assumption|principle|invariant|conservation|bound) ]]; then
  emit theory implement-method
  exit 0
fi

exit 1
