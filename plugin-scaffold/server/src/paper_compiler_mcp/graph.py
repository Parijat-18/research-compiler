from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

# v1.0: component vocabulary matches ATOM_CATEGORIES (domain-neutral).
# A "component" in trace_dependency is a logical layer of the paper's
# implementation — method, objective, data, etc. — that may be common
# across fields. Mappings are 1:1 to roles and categories so the MCP
# trace tool works regardless of domain.
ROLE_TO_COMPONENT = {
    "method_dependency": "method",
    "objective_dependency": "objective",
    "data_dependency": "data",
    "preprocessing_dependency": "preprocessing",
    "evaluation_dependency": "evaluation",
    "baseline_dependency": "baseline",
    "procedure_dependency": "procedure",
    "theory_dependency": "theory",
}
COMPONENT_TO_ROLE = {v: k for k, v in ROLE_TO_COMPONENT.items()}
ATOM_CATEGORY_TO_COMPONENT = {
    "method": "method",
    "objective": "objective",
    "data": "data",
    "preprocessing": "preprocessing",
    "evaluation": "evaluation",
    "baseline": "baseline",
    "procedure": "procedure",
    "parameter": "procedure",   # parameters are run-time procedural values
    "theory": "theory",
}


@dataclass
class _Indexes:
    bm25: Optional[Any] = None
    bm25_corpus: list[str] | None = None
    bm25_atom_ids: list[str] | None = None
    embeddings: Optional[Any] = None
    embedding_atom_ids: list[str] | None = None
    embedder: Optional[Any] = None


class ResearchGraph:
    def __init__(self, doc: dict[str, Any], research_dir: Path) -> None:
        self.doc = doc
        self.research_dir = research_dir
        self.papers: dict[str, dict] = doc.get("papers", {}) or {}
        self.atoms: dict[str, dict] = doc.get("atoms", {}) or {}
        self.evidence: dict[str, dict] = doc.get("evidence", {}) or {}
        self.edges: dict[str, dict] = doc.get("edges", {}) or {}
        self.missing: list[dict] = doc.get("missing_details", []) or []
        self.order: list[dict] = doc.get("implementation_order", []) or []
        self.indexes = _Indexes()
        # uid → atom_id lookup so MCP callers can pass either identifier.
        self._uid_index: dict[str, str] = {
            a["uid"]: aid for aid, a in self.atoms.items() if a.get("uid")
        }

    def _resolve_atom(self, key: str) -> Optional[dict]:
        """Look up an atom by either its display id ('atom-001') or its uid."""
        if not key:
            return None
        a = self.atoms.get(key)
        if a is not None:
            return a
        mapped = self._uid_index.get(key)
        return self.atoms.get(mapped) if mapped else None

    # ---------- loading ----------

    @classmethod
    def load(cls, research_dir: Path) -> Optional["ResearchGraph"]:
        path = research_dir / "graph.json"
        if not path.exists():
            return None
        try:
            doc = json.loads(path.read_text())
        except json.JSONDecodeError:
            return None
        return cls(doc, research_dir)

    # ---------- tools ----------

    def stats(self) -> dict:
        return {
            "schema_version": self.doc.get("schema_version"),
            "compiled_at": self.doc.get("compiled_at"),
            "target_paper_id": self.doc.get("target_paper_id"),
            "papers": len(self.papers),
            "atoms": len(self.atoms),
            "evidence_spans": len(self.evidence),
            "edges": len(self.edges),
            "missing_details": len(self.missing),
            "build_stats": self.doc.get("build_stats", {}),
        }

    def paper_summary(self, paper_id: str) -> dict:
        rec = self.papers.get(paper_id)
        if not rec:
            return {"error": f"paper {paper_id!r} not in graph"}
        defines = [a for a in self.atoms.values() if a.get("defined_by_paper_id") == paper_id]
        uses = [a for a in self.atoms.values() if paper_id in (a.get("used_by_paper_ids") or [])]
        return {
            "paper_id": paper_id,
            "metadata": rec.get("metadata", {}),
            "external_ids": rec.get("external_ids", {}),
            "is_target": rec.get("is_target", False),
            "rank": rec.get("rank"),
            "atoms_defined": [{"id": a["id"], "uid": a.get("uid"), "name": a["name"], "category": a["category"]} for a in defines],
            "atoms_used": [{"id": a["id"], "uid": a.get("uid"), "name": a["name"], "category": a["category"]} for a in uses],
        }

    def trace(self, component: str) -> dict:
        if component not in COMPONENT_TO_ROLE:
            return {"error": f"unknown component {component!r}", "valid": sorted(COMPONENT_TO_ROLE)}
        atoms_in_cat = [a for a in self.atoms.values() if ATOM_CATEGORY_TO_COMPONENT.get(a.get("category")) == component]
        atoms_in_cat.sort(key=lambda a: -a.get("priority", 0))
        target_id = self.doc.get("target_paper_id")
        chain: list[dict] = []
        seen_papers: set[str] = set()
        for atom in atoms_in_cat:
            defining = atom.get("defined_by_paper_id")
            paper = self.papers.get(defining, {})
            chain.append(
                {
                    "atom_id": atom["id"],
                    "atom_uid": atom.get("uid"),
                    "atom_name": atom["name"],
                    "category": atom["category"],
                    "defined_by_paper_id": defining,
                    "defined_by_title": (paper.get("metadata") or {}).get("title"),
                    "used_by": atom.get("used_by_paper_ids", []),
                    "evidence_span_ids": atom.get("evidence_span_ids", []),
                    "priority": atom.get("priority"),
                }
            )
            seen_papers.add(defining)
        # also surface edges whose best_role maps to this component
        related_edges = [
            e for e in self.edges.values() if ROLE_TO_COMPONENT.get(e.get("best_role")) == component
        ]
        return {
            "component": component,
            "target_paper_id": target_id,
            "atom_chain": chain,
            "supporting_edges": [
                {
                    "edge_id": e["edge_id"],
                    "to_paper_id": e["to_paper_id"],
                    "section_type": e.get("section_type"),
                    "confidence": e.get("best_confidence"),
                    "context_excerpt": (e.get("context") or "")[:200],
                }
                for e in related_edges[:25]
            ],
        }

    def search_atoms(self, query: str, limit: int = 5) -> list[dict]:
        self._ensure_indexes()
        hits: list[tuple[float, dict]] = []
        if self.indexes.bm25 is not None:
            tokens = _tokenize(query)
            scores = self.indexes.bm25.get_scores(tokens)
            ranked = sorted(zip(self.indexes.bm25_atom_ids or [], scores), key=lambda kv: kv[1], reverse=True)
            for atom_id, score in ranked[: limit * 3]:
                if score <= 0:
                    continue
                atom = self.atoms.get(atom_id)
                if atom:
                    hits.append((float(score), {**atom, "_bm25": float(score)}))

        if self.indexes.embeddings is not None and self.indexes.embedder is not None:
            try:
                import numpy as np

                q = self.indexes.embedder.encode([query], normalize_embeddings=True)[0]
                sims = self.indexes.embeddings @ q
                ranked = sorted(zip(self.indexes.embedding_atom_ids or [], sims.tolist()), key=lambda kv: kv[1], reverse=True)
                seen = {h[1]["id"] for h in hits}
                for atom_id, sim in ranked[: limit * 3]:
                    if atom_id in seen or sim < 0.2:
                        continue
                    atom = self.atoms.get(atom_id)
                    if atom:
                        hits.append((float(sim), {**atom, "_vector": float(sim)}))
            except Exception:  # noqa: BLE001
                pass

        # naive fallback: substring match
        if not hits:
            q_low = query.lower()
            for atom in self.atoms.values():
                if q_low in atom.get("name", "").lower() or q_low in atom.get("description", "").lower():
                    hits.append((1.0, atom))

        hits.sort(key=lambda kv: kv[0], reverse=True)
        seen_ids: set[str] = set()
        out: list[dict] = []
        for _, atom in hits:
            if atom["id"] in seen_ids:
                continue
            seen_ids.add(atom["id"])
            out.append(
                {
                    "id": atom["id"],
                    "uid": atom.get("uid"),
                    "name": atom["name"],
                    "category": atom["category"],
                    "description": atom.get("description"),
                    "defined_by_paper_id": atom.get("defined_by_paper_id"),
                    "score": atom.get("_vector", atom.get("_bm25", 1.0)),
                }
            )
            if len(out) >= limit:
                break
        return out

    def evidence_for(self, atom_id: str) -> list[dict]:
        atom = self._resolve_atom(atom_id)
        if not atom:
            return [{"error": f"atom {atom_id!r} not found (tried both atom_id and atom_uid)"}]
        spans = []
        for eid in atom.get("evidence_span_ids", []):
            ev = self.evidence.get(eid)
            if not ev:
                continue
            paper = self.papers.get(ev.get("paper_id"), {})
            spans.append(
                {
                    "id": ev["id"],
                    "paper_id": ev.get("paper_id"),
                    "paper_title": (paper.get("metadata") or {}).get("title"),
                    "section_id": ev.get("section_id"),
                    "section_type": ev.get("section_type"),
                    "paragraph_id": ev.get("paragraph_id"),
                    "char_start": ev.get("char_start"),
                    "char_end": ev.get("char_end"),
                    "verbatim_text": ev.get("verbatim_text"),
                }
            )
        return spans

    def missing_details(self) -> list[dict]:
        return list(self.missing)

    def find_equation(self, symbol_or_keyword: str) -> list[dict]:
        # Equations live inside cached IRs, not in graph.json — return empty unless we have a cached map.
        eqfile = self.research_dir / "equations.json"
        if not eqfile.exists():
            return []
        try:
            data = json.loads(eqfile.read_text())
        except json.JSONDecodeError:
            return []
        q = symbol_or_keyword.lower()
        return [eq for eq in data if q in (eq.get("latex") or "").lower()][:10]

    def compare(self, atom_a: str, atom_b: str) -> dict:
        a = self._resolve_atom(atom_a)
        b = self._resolve_atom(atom_b)
        if not a or not b:
            return {"error": "one or both atoms not found", "a_found": bool(a), "b_found": bool(b)}
        return {
            "a": {
                "id": a["id"],
                "uid": a.get("uid"),
                "name": a["name"],
                "category": a["category"],
                "description": a.get("description"),
                "evidence": self.evidence_for(a["id"]),
            },
            "b": {
                "id": b["id"],
                "uid": b.get("uid"),
                "name": b["name"],
                "category": b["category"],
                "description": b.get("description"),
                "evidence": self.evidence_for(b["id"]),
            },
            "same_category": a["category"] == b["category"],
            "shared_users": sorted(set(a.get("used_by_paper_ids", [])) & set(b.get("used_by_paper_ids", []))),
        }

    def neighbors(self, paper_id: str, role: Optional[str] = None) -> list[dict]:
        out: list[dict] = []
        for e in self.edges.values():
            if e.get("from_paper_id") != paper_id and e.get("to_paper_id") != paper_id:
                continue
            if role and not any(r.get("label") == role for r in e.get("roles", [])):
                continue
            other = e["to_paper_id"] if e["from_paper_id"] == paper_id else e["from_paper_id"]
            paper = self.papers.get(other, {})
            out.append(
                {
                    "paper_id": other,
                    "title": (paper.get("metadata") or {}).get("title"),
                    "best_role": e.get("best_role"),
                    "best_confidence": e.get("best_confidence"),
                    "section_type": e.get("section_type"),
                    "context_excerpt": (e.get("context") or "")[:200],
                }
            )
        return out

    # ---------- indexes ----------

    def _ensure_indexes(self) -> None:
        if not self.atoms:
            return
        if self.indexes.bm25 is None:
            try:
                from rank_bm25 import BM25Okapi
            except ImportError:
                return
            atom_ids = list(self.atoms.keys())
            corpus = [_atom_text(self.atoms[a], self.evidence) for a in atom_ids]
            tokenized = [_tokenize(d) for d in corpus]
            self.indexes.bm25 = BM25Okapi(tokenized)
            self.indexes.bm25_atom_ids = atom_ids
            self.indexes.bm25_corpus = corpus

        emb_path = self.research_dir / "embeddings.npy"
        meta_path = self.research_dir / "embeddings.json"
        if self.indexes.embeddings is None and emb_path.exists() and meta_path.exists():
            try:
                import numpy as np

                self.indexes.embeddings = np.load(emb_path)
                self.indexes.embedding_atom_ids = json.loads(meta_path.read_text()).get("atom_ids", [])
                self.indexes.embedder = _load_embedder()
            except Exception:  # noqa: BLE001
                self.indexes.embeddings = None


def _atom_text(atom: dict, evidence: dict[str, dict]) -> str:
    parts = [atom.get("name", ""), atom.get("category", ""), atom.get("description", "")]
    for eid in atom.get("evidence_span_ids", []):
        ev = evidence.get(eid)
        if ev:
            parts.append(ev.get("verbatim_text", ""))
    return " ".join(parts)


_TOKEN_RE = re.compile(r"[A-Za-z0-9_-]+")


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text)]


def _load_embedder():
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        return None
    for name in ("allenai-specter", "BAAI/bge-small-en-v1.5"):
        try:
            return SentenceTransformer(name)
        except Exception:  # noqa: BLE001
            continue
    return None
