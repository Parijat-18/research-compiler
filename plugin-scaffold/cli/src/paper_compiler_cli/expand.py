from __future__ import annotations

import asyncio
import re
import sys
import time
from dataclasses import dataclass, field
from typing import Optional

from .config import Config
from .ir import Paper, Reference, SectionType
from .resolve import Candidate
from .s2_client import S2Client


@dataclass
class NeighborPaper:
    paper_id: str
    record: dict
    depth: int
    priority: float
    parsed: Optional[Paper] = None
    acquired: bool = False
    reasons: list[str] = field(default_factory=list)


@dataclass
class Neighborhood:
    target: Paper
    papers: dict[str, NeighborPaper]
    edges: list["RawEdge"]
    stats: dict


@dataclass
class RawEdge:
    edge_id: str
    from_paper_id: str
    to_paper_id: str
    section_id: str
    section_type: SectionType
    paragraph_id: str
    context: str
    nearby_equation_ids: list[str]
    nearby_algorithm_ids: list[str]
    nearby_table_ids: list[str]


SECTION_PRIORITY: dict[SectionType, float] = {
    "method": 1.0,
    "experiments": 0.8,
    "results": 0.6,
    "discussion": 0.4,
    "introduction": 0.3,
    "abstract": 0.2,
    "related_work": 0.15,
    "conclusion": 0.2,
    "appendix": 0.5,
    "other": 0.3,
}


def _ref_lookup(target: Paper) -> dict[str, str]:
    out: dict[str, str] = {}
    for ref in target.references:
        if ref.resolved_paper_id:
            out[ref.ref_id] = ref.resolved_paper_id
    return out


_BIB_FIELD_RE = re.compile(r"(\w+)\s*=\s*\{?([^,{}]+?)\}?\s*(?:,|$)")


def _parse_bib_raw(raw: str) -> dict[str, str]:
    """Extract title/author/year/url from a bibtex-flattened raw string."""
    fields: dict[str, str] = {}
    for m in _BIB_FIELD_RE.finditer(raw or ""):
        k = m.group(1).lower()
        v = m.group(2).strip()
        if k in {"title", "author", "year", "url", "journal", "booktitle"}:
            fields[k] = v
    return fields


def _author_last_names(author_field: str) -> list[str]:
    parts = re.split(r"\s+and\s+|;", author_field)
    out: list[str] = []
    for p in parts:
        p = p.strip().strip(",")
        if not p:
            continue
        # "Last, First" or "First Last"
        if "," in p:
            last = p.split(",", 1)[0].strip()
        else:
            last = p.rsplit(" ", 1)[-1].strip()
        last = re.sub(r"[^A-Za-z]+", "", last).lower()
        if last:
            out.append(last)
    return out


async def _resolve_references(client: S2Client, target: Paper) -> dict[str, str]:
    unresolved = [r for r in target.references if not r.resolved_paper_id]
    if not unresolved:
        return _ref_lookup(target)

    queries: list[tuple[str, str]] = []
    for ref in unresolved:
        raw = ref.raw or ref.marker
        fields = _parse_bib_raw(raw)

        # 1. arXiv identifier (in raw OR url field).
        m_arxiv = re.search(r"(\d{4}\.\d{4,5})", raw) or re.search(r"(\d{4}\.\d{4,5})", fields.get("url", ""))
        # 2. DOI
        m_doi = re.search(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", raw, re.IGNORECASE) or re.search(
            r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", fields.get("url", ""), re.IGNORECASE
        )
        if m_arxiv:
            queries.append((ref.ref_id, f"ARXIV:{m_arxiv.group(1)}"))
        elif m_doi:
            queries.append((ref.ref_id, f"DOI:{m_doi.group(0)}"))

    for ref_id, token in queries:
        rec = await client.get_paper(token, fields="paperId")
        if rec and rec.get("paperId"):
            for r in target.references:
                if r.ref_id == ref_id:
                    r.resolved_paper_id = f"s2:{rec['paperId']}"
                    r.resolution_confidence = 0.97
                    break

    # 3. Search by title (+ author/year disambiguation) for the rest.
    still = [r for r in target.references if not r.resolved_paper_id and r.raw]
    sem = asyncio.Semaphore(4)

    async def _search(r) -> None:
        async with sem:
            fields = _parse_bib_raw(r.raw)
            title = fields.get("title", "")
            author = fields.get("author", "")
            year = fields.get("year", "")
            authors_expected = _author_last_names(author)

            if title:
                q = title
                if author:
                    first_author = authors_expected[0] if authors_expected else ""
                    if first_author:
                        q = f"{title} {first_author}"
            else:
                q = r.raw[:200]
            q = re.sub(r"[{}\\]", "", q)[:200]

            results = await client.search(q, limit=3)
            if not results:
                return
            # Score each candidate by author overlap + year match.
            best = None
            best_score = -1.0
            for rec in results:
                rec_authors = {_norm(a.get("name", "")).split()[-1] for a in rec.get("authors") or [] if a.get("name")}
                rec_year = rec.get("year")
                score = 0.0
                if authors_expected:
                    overlap = sum(1 for a in authors_expected if a in rec_authors)
                    score += min(1.0, overlap / max(1, len(authors_expected)))
                if year and rec_year and str(rec_year) == str(year).strip("{}"):
                    score += 0.4
                # title overlap fallback
                if title and rec.get("title"):
                    rec_t = _norm(rec.get("title"))
                    qt = _norm(title)
                    inter = len(set(rec_t.split()) & set(qt.split()))
                    score += min(0.6, inter / 20.0)
                if score > best_score:
                    best_score = score
                    best = rec

            if best and best_score >= 0.4:
                r.resolved_paper_id = f"s2:{best['paperId']}"
                r.resolution_confidence = min(0.9, 0.4 + best_score / 2)

    await asyncio.gather(*(_search(r) for r in still[:120]))
    return _ref_lookup(target)


def _norm(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9 ]+", " ", s.lower())


def _build_raw_edges(target: Paper, ref_to_pid: dict[str, str]) -> list[RawEdge]:
    edges: list[RawEdge] = []
    occ_counts: dict[tuple[str, str], int] = {}
    for sec in target.sections:
        for para in sec.paragraphs:
            for cit in para.citations:
                pid = cit.resolved_paper_id or ref_to_pid.get(cit.ref_id)
                if not pid:
                    continue
                key = (target.paper_id, pid)
                occ_counts[key] = occ_counts.get(key, 0) + 1
                edge_id = f"{target.paper_id}::{pid}::{occ_counts[key]}"
                edges.append(
                    RawEdge(
                        edge_id=edge_id,
                        from_paper_id=target.paper_id,
                        to_paper_id=pid,
                        section_id=sec.id,
                        section_type=sec.section_type,
                        paragraph_id=para.id,
                        context=para.text[:600],
                        nearby_equation_ids=list(para.equation_refs),
                        nearby_algorithm_ids=list(para.algorithm_refs),
                        nearby_table_ids=list(para.table_refs),
                    )
                )
    return edges


def _priority(edges_for_pid: list[RawEdge], influential: bool) -> float:
    if not edges_for_pid:
        return 0.0
    p = 0.0
    for e in edges_for_pid:
        p += SECTION_PRIORITY.get(e.section_type, 0.3)
        if e.nearby_equation_ids:
            p += 0.4
        if e.nearby_algorithm_ids:
            p += 0.3
        if e.nearby_table_ids:
            p += 0.2
    p += 0.1 * (len(edges_for_pid) - 1)
    if influential:
        p += 0.2
    return p


async def _seed_from_s2_references(client: S2Client, target: Paper) -> None:
    """Augment target.references using S2's references-of-paper endpoint.

    Matches S2 records against existing references (by title token overlap, or
    by arXiv id) to backfill resolved_paper_id without re-uploading the bib.
    Also appends any S2 references not already present.
    """
    s2_id = target.paper_id.replace("s2:", "")
    s2_refs = await client.references(s2_id)
    if not s2_refs:
        return

    def _tokens(s: str) -> set[str]:
        return {t for t in re.findall(r"[a-z0-9]+", s.lower()) if len(t) > 3}

    existing_by_tokens: list[tuple[set[str], object]] = [
        (_tokens(r.raw or ""), r) for r in target.references if not r.resolved_paper_id
    ]

    seen_pids = {r.resolved_paper_id for r in target.references if r.resolved_paper_id}

    for rec in s2_refs:
        rec_pid = f"s2:{rec['paperId']}" if rec.get("paperId") else None
        if not rec_pid:
            continue
        rec_title = (rec.get("title") or "").strip()
        rec_arxiv = (rec.get("externalIds") or {}).get("ArXiv")
        matched = False

        title_tokens = _tokens(rec_title)
        for ex_tokens, ref in existing_by_tokens:
            if rec_arxiv and rec_arxiv in (ref.raw or ""):
                ref.resolved_paper_id = rec_pid
                ref.resolution_confidence = 0.97
                matched = True
                break
            if title_tokens and ex_tokens:
                overlap = len(title_tokens & ex_tokens)
                if overlap >= max(3, int(0.5 * len(title_tokens))):
                    ref.resolved_paper_id = rec_pid
                    ref.resolution_confidence = 0.85
                    matched = True
                    break

        if not matched and rec_pid not in seen_pids:
            new_id = f"ref-s2-{len(target.references) + 1}"
            target.references.append(
                Reference(
                    ref_id=new_id,
                    marker=f"[s2:{rec_pid}]",
                    raw=rec_title or rec_pid,
                    resolved_paper_id=rec_pid,
                    resolution_confidence=0.7,
                )
            )
            seen_pids.add(rec_pid)


async def expand_neighborhood(cfg: Config, target: Paper) -> Neighborhood:
    started = time.time()
    deadline = started + cfg.compile.max_wall_seconds
    papers: dict[str, NeighborPaper] = {}

    async with S2Client(cfg) as client:
        ref_to_pid = await _resolve_references(client, target)

        # If local parse yielded too few resolved refs, augment with the S2
        # references endpoint. This handles papers with broken bib parses or
        # bib entries that lack arXiv/DOI fields.
        resolved_local = sum(1 for r in target.references if r.resolved_paper_id)
        if resolved_local < max(5, int(0.3 * max(len(target.references), 1))):
            await _seed_from_s2_references(client, target)
            ref_to_pid = _ref_lookup(target)

        edges = _build_raw_edges(target, ref_to_pid)

        # Synthesize phantom edges for resolved references that produced no
        # paragraph-level citation (common when the bib has more entries than
        # the body cites, or when refs come from the S2 references endpoint).
        cited_pids = {e.to_paper_id for e in edges}
        for ref in target.references:
            if not ref.resolved_paper_id or ref.resolved_paper_id in cited_pids:
                continue
            pid = ref.resolved_paper_id
            edges.append(
                RawEdge(
                    edge_id=f"{target.paper_id}::{pid}::ref",
                    from_paper_id=target.paper_id,
                    to_paper_id=pid,
                    section_id="",
                    section_type="other",
                    paragraph_id="",
                    context=(ref.raw or "")[:600],
                    nearby_equation_ids=[],
                    nearby_algorithm_ids=[],
                    nearby_table_ids=[],
                )
            )
            cited_pids.add(pid)

        # group edges by to_paper_id, gather influential signal via batch
        pid_to_edges: dict[str, list[RawEdge]] = {}
        for e in edges:
            pid_to_edges.setdefault(e.to_paper_id, []).append(e)

        s2_ids = [pid.replace("s2:", "") for pid in pid_to_edges]
        batched = await client.batch(s2_ids) if s2_ids else []
        recs_by_id: dict[str, dict] = {}
        for rec in batched:
            if rec and rec.get("paperId"):
                recs_by_id[f"s2:{rec['paperId']}"] = rec

        for pid, e_list in pid_to_edges.items():
            rec = recs_by_id.get(pid, {})
            influential = bool(rec.get("influentialCitationCount", 0) and rec.get("influentialCitationCount", 0) > 5)
            pri = _priority(e_list, influential)
            papers[pid] = NeighborPaper(paper_id=pid, record=rec, depth=1, priority=pri)

        # cap to max_papers, sort by priority
        ranked = sorted(papers.values(), key=lambda np: np.priority, reverse=True)
        papers = {np.paper_id: np for np in ranked[: cfg.compile.max_papers]}

        # depth-2 expansion: top-K depth-1 papers, fetch their references
        if cfg.compile.max_depth >= 2 and client.stats.requests < cfg.compile.max_s2_requests and time.time() < deadline:
            top = ranked[: cfg.compile.expand_top_k]
            for parent in top:
                if time.time() >= deadline or client.stats.requests >= cfg.compile.max_s2_requests:
                    break
                refs = await client.references(parent.paper_id.replace("s2:", ""))
                for r in refs[:30]:
                    cpid = f"s2:{r['paperId']}" if r.get("paperId") else None
                    if not cpid or cpid in papers:
                        continue
                    # inherit a fraction of parent's implementation priority,
                    # so top-K depth-2 papers pass the acquisition gate.
                    d2_prio = 0.5 * parent.priority
                    papers[cpid] = NeighborPaper(
                        paper_id=cpid,
                        record=r,
                        depth=2,
                        priority=d2_prio,
                        reasons=[f"depth2 via {parent.paper_id}"],
                    )

        # Acquire + parse cited papers so we have real text to chunk/embed.
        # Depth 1 → everything (subject to time + max-papers caps).
        # Depth 2 → only the top-K by priority.
        await _acquire_neighborhood(cfg, papers, deadline)

        stats = {
            "papers_seen": len(papers),
            "papers_acquired": sum(1 for p in papers.values() if p.acquired),
            "papers_parsed": sum(1 for p in papers.values() if p.parsed is not None),
            "s2_requests": client.stats.requests,
            "s2_cache_hits": client.stats.cache_hits,
            "elapsed": time.time() - started,
        }
        print(f"expand: {stats}", file=sys.stderr)

    return Neighborhood(target=target, papers=papers, edges=edges, stats=stats)


async def _acquire_neighborhood(cfg: Config, papers: dict[str, "NeighborPaper"], deadline: float) -> None:
    """Acquire + parse cited papers in parallel, respecting depth + time."""
    from .acquire import acquire as _acquire
    from .parse import parse_paper as _parse
    from .resolve import Candidate
    from .ir import ExternalIds

    sem = asyncio.Semaphore(4)

    async def _one(np: "NeighborPaper") -> None:
        if time.time() >= deadline:
            return
        if np.depth >= 2 and np.priority < 0.5:
            return  # only top-K depth-2 papers get acquired
        async with sem:
            rec = np.record or {}
            ext = rec.get("externalIds") or {}
            cand = Candidate(
                paper_id=np.paper_id,
                title=rec.get("title") or "",
                year=rec.get("year"),
                authors=[a.get("name", "") for a in rec.get("authors") or []],
                external_ids=ExternalIds(
                    arxiv=ext.get("ArXiv"),
                    doi=ext.get("DOI"),
                    corpus_id=str(rec.get("corpusId")) if rec.get("corpusId") else None,
                ),
                confidence=1.0,
                abstract=rec.get("abstract"),
            )
            try:
                acq = await _acquire(cfg, cand)
            except Exception as e:  # noqa: BLE001
                print(f"acquire failed for {np.paper_id}: {e}", file=sys.stderr)
                return
            if acq is None:
                return
            np.acquired = True
            try:
                np.parsed = await _parse(cfg, cand, acq)
            except Exception as e:  # noqa: BLE001
                print(f"parse failed for {np.paper_id}: {e}", file=sys.stderr)
                return

    await asyncio.gather(*(_one(np) for np in papers.values()))
