from __future__ import annotations

import time
from typing import Any

from ..atoms import Atom, EvidenceSpan, MissingDetail
from ..atoms.extract import collect_missing_details
from ..classify.edge import ClassifiedEdge, best_role
from ..expand import Neighborhood
from ..ir import Paper

SCHEMA_VERSION = "1.0"


def _paper_node(target: Paper, neighborhood: Neighborhood, scores: dict[str, dict[str, float]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    out[target.paper_id] = {
        "metadata": target.metadata.model_dump(exclude_none=True),
        "external_ids": target.external_ids.model_dump(exclude_none=True),
        "scholarly_influence": scores.get(target.paper_id, {}).get("scholarly_influence", 0.0),
        "implementation_influence": scores.get(target.paper_id, {}).get("implementation_influence", 0.0),
        "rank": scores.get(target.paper_id, {}).get("rank", 1.0),
        "is_target": True,
        "acquired": True,
    }
    for pid, np in neighborhood.papers.items():
        rec = np.record or {}
        out[pid] = {
            "metadata": {
                "title": rec.get("title"),
                "year": rec.get("year"),
                "venue": rec.get("venue"),
                "authors": [a.get("name") for a in rec.get("authors") or []],
                "abstract": rec.get("abstract"),
            },
            "external_ids": rec.get("externalIds") or {},
            "scholarly_influence": scores.get(pid, {}).get("scholarly_influence", 0.0),
            "implementation_influence": scores.get(pid, {}).get("implementation_influence", 0.0),
            "rank": scores.get(pid, {}).get("rank", 0.0),
            "is_target": False,
            "acquired": np.acquired,
            "depth": np.depth,
        }
    return out


def _edge_node(edges: list[ClassifiedEdge], atoms: list[Atom]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    atom_by_edge: dict[str, list[str]] = {}
    for a in atoms:
        for ev in a.evidence_span_ids:
            atom_by_edge.setdefault(ev, []).append(a.id)
    for ce in edges:
        role, conf = best_role(ce)
        out[ce.edge.edge_id] = {
            "edge_id": ce.edge.edge_id,
            "from_paper_id": ce.edge.from_paper_id,
            "to_paper_id": ce.edge.to_paper_id,
            "roles": [{"label": r.label, "confidence": round(r.confidence, 3)} for r in ce.roles],
            "context": ce.edge.context,
            "section_id": ce.edge.section_id,
            "section_type": ce.edge.section_type,
            "paragraph_id": ce.edge.paragraph_id,
            "nearby_equation_ids": ce.edge.nearby_equation_ids,
            "nearby_algorithm_ids": ce.edge.nearby_algorithm_ids,
            "nearby_table_ids": ce.edge.nearby_table_ids,
            "classifier": ce.classifier,
            "best_role": role,
            "best_confidence": round(conf, 3),
        }
    return out


def _atom_node(atoms: list[Atom]) -> dict[str, Any]:
    return {
        a.id: {
            "id": a.id,
            "name": a.name,
            "category": a.category,
            "defined_by_paper_id": a.defined_by_paper_id,
            "used_by_paper_ids": a.used_by_paper_ids,
            "description": a.description,
            "evidence_span_ids": a.evidence_span_ids,
            "equation_refs": a.equation_refs,
            "priority": a.priority,
            "dependencies": a.dependencies,
        }
        for a in atoms
    }


def _evidence_node(evidence: list[EvidenceSpan]) -> dict[str, Any]:
    return {
        e.id: {
            "id": e.id,
            "paper_id": e.paper_id,
            "section_id": e.section_id,
            "section_type": e.section_type,
            "verbatim_text": e.verbatim_text,
            "char_range": list(e.char_range) if e.char_range else None,
            "supports_atom_ids": e.supports_atom_ids,
        }
        for e in evidence
    }


def _missing_node(details: list[MissingDetail]) -> list[dict[str, Any]]:
    return [
        {
            "id": d.id,
            "question": d.question,
            "category": d.category,
            "options": d.options,
            "suggested_default": d.suggested_default,
            "rationale": d.rationale,
        }
        for d in details
    ]


def build_graph_doc(
    target: Paper,
    neighborhood: Neighborhood,
    atoms: list[Atom],
    evidence: list[EvidenceSpan],
    edges: list[ClassifiedEdge],
    scores: dict[str, dict[str, float]],
    order: list[dict],
    elapsed: float,
) -> dict[str, Any]:
    missing = collect_missing_details(target, atoms)
    n_attempted = sum(1 for r in target.references)
    n_resolved = sum(1 for r in target.references if r.resolved_paper_id)
    return {
        "schema_version": SCHEMA_VERSION,
        "compiled_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "target_paper_id": target.paper_id,
        "papers": _paper_node(target, neighborhood, scores),
        "atoms": _atom_node(atoms),
        "evidence": _evidence_node(evidence),
        "edges": _edge_node(edges, atoms),
        "missing_details": _missing_node(missing),
        "implementation_order": order,
        "build_stats": {
            "papers_resolved": n_resolved,
            "papers_attempted": n_attempted,
            "papers_in_neighborhood": len(neighborhood.papers),
            "atoms_extracted": len(atoms),
            "evidence_spans": len(evidence),
            "edges": len(edges),
            "wall_time_seconds": round(elapsed, 1),
            **neighborhood.stats,
        },
    }
