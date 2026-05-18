from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from ..ir import Paper


def write_manifest(path: Path, graph: dict[str, Any], target: Paper, started: float) -> None:
    stats = graph.get("build_stats", {})
    n_resolved = stats.get("papers_resolved", 0)
    n_attempted = stats.get("papers_attempted", 0)
    coverage = (n_resolved / n_attempted) if n_attempted else 0.0
    manifest = {
        "target_paper_id": target.paper_id,
        "title": target.metadata.title,
        "compiled_at": graph.get("compiled_at"),
        "wall_time_seconds": round(time.time() - started, 1),
        "coverage": {
            "references_attempted": n_attempted,
            "references_resolved": n_resolved,
            "coverage_pct": round(coverage * 100, 1),
        },
        "counts": {
            "papers_in_neighborhood": stats.get("papers_in_neighborhood", 0),
            "atoms_extracted": stats.get("atoms_extracted", 0),
            "evidence_spans": stats.get("evidence_spans", 0),
            "edges": stats.get("edges", 0),
            "missing_details": len(graph.get("missing_details", [])),
        },
        "failures": [],
        "s2": {
            "requests": stats.get("s2_requests", 0),
            "cache_hits": stats.get("s2_cache_hits", 0),
        },
        "llm_backend": stats.get("llm_backend", "none"),
    }
    path.write_text(json.dumps(manifest, indent=2))
