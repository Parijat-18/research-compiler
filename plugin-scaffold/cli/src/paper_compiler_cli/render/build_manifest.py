from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from ..graph_db import SCHEMA_VERSION
from ..ir import Paper


def write_manifest(path: Path, graph: dict[str, Any], target: Paper, started: float) -> None:
    stats = graph.get("build_stats", {})
    n_resolved = stats.get("papers_resolved", 0)
    n_attempted = stats.get("papers_attempted", 0)
    coverage = (n_resolved / n_attempted) if n_attempted else 0.0
    ev_total = stats.get("evidence_total", 0)
    ev_resolved = stats.get("evidence_chunk_resolved", 0)
    papers_by_source = stats.get("papers_by_source", {}) or {}
    manifest = {
        "schema_version": SCHEMA_VERSION,
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
        "evidence_provenance": {
            "total": ev_total,
            "chunk_id_resolved": ev_resolved,
            "resolved_pct": round(100 * ev_resolved / ev_total, 1) if ev_total else 0.0,
        },
        "papers_by_source": dict(sorted(papers_by_source.items(), key=lambda kv: -kv[1])),
        "failures": [],
        "s2": {
            "requests": stats.get("s2_requests", 0),
            "cache_hits": stats.get("s2_cache_hits", 0),
        },
        "llm_backend": stats.get("llm_backend", "none"),
    }
    path.write_text(json.dumps(manifest, indent=2))
