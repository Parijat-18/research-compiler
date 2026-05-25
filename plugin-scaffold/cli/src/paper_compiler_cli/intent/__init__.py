"""Citation-intent classification (Phase 4).

The single largest noise contributor in v0.2 was that **60% of edges were
``related_work_only`` passing mentions** weighted identically to
load-bearing dependencies. This subpackage adds a SciCite-style citation
intent on every edge, then combines it with the existing role to produce a
single signal-weighted ``edges.weight`` that retrieval and traversal can
use to suppress noise.

Six labels (SciCite + ACL-ARC hybrid):

- ``mention``    — passing reference; "for further work see [3]"
- ``background`` — situating the paper in prior literature
- ``result``     — citing the cited paper's empirical results
- ``method``     — using a method/architecture/loss from the cited paper
- ``extends``    — directly extending the cited work
- ``contrasts``  — disagrees with / refutes / fails to reproduce

``INTENT_WEIGHT`` is the multiplier applied to ``best_confidence × role_weight``
when computing the final per-edge ``weight``. The numbers below reflect the
audit finding that ``mention`` and ``background`` citations drown out
load-bearing ``method``/``extends`` citations in retrieval. The bias is
intentional — a paper citing 30 background references and 3 method
references should rank the 3 method references higher.

Future work (deferred, post-v1.0):
- Swap heuristic+LLM for ONNX SciBERT fine-tuned on SciCite (see
  https://github.com/allenai/scicite). The shape of this module is designed
  so that a future ``intent/scicite.py`` can drop in without touching the
  caller — it just needs to expose ``classify_intent(edge, neighbor) ->
  IntentResult``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

INTENT_LABELS = (
    "mention",
    "background",
    "result",
    "method",
    "extends",
    "contrasts",
)

# Multiplier applied to edge weight. Tuned so a method/extends edge with
# 0.8 role confidence beats a background edge with 0.95 role confidence.
INTENT_WEIGHT: dict[str, float] = {
    "mention": 0.2,
    "background": 0.4,
    "result": 0.8,
    "method": 1.2,
    "extends": 1.5,
    "contrasts": 1.0,
}


@dataclass
class IntentResult:
    """Output of one citation-intent classification.

    ``intents`` carries the full ranked list when multiple intents apply
    (a single citation often plays multiple roles, e.g. method + result —
    the SciCite paper's multi-label observation). ``best_label`` /
    ``best_confidence`` is the top entry for convenience.
    """

    best_label: str
    best_confidence: float
    intents: list[dict] = field(default_factory=list)  # [{"label": ..., "confidence": ...}]
    source: str = "heuristic"  # "heuristic" | "llm"


def intent_weight(label: str | None) -> float:
    if not label:
        return 1.0
    return INTENT_WEIGHT.get(label, 1.0)
