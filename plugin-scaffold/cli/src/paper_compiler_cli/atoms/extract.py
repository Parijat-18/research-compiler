from __future__ import annotations

import hashlib
import json
import re
import sys
from typing import Optional

from ..classify import ROLE_TO_CATEGORY  # role → category, domain-neutral (v1.0)
from ..classify.edge import ClassifiedEdge, best_role
from ..config import Config
from ..expand import Neighborhood
from ..ir import Paper, Paragraph, Section
from . import ATOM_CATEGORIES, Atom, EvidenceSpan, MissingDetail

# When the canonical-name normalizer changes, bump this so old UIDs
# don't collide silently with newly-shaped ones.
ATOM_UID_NORMALIZER_VERSION = "v1"

# v1.0: domain-neutral named-entity regexes. The v0.2 NAMED_LOSS_RE /
# NAMED_ARCH_RE / NAMED_DATASET_KNOWN_RE / NAMED_OPT_RE / HYPER_RE were
# all hardcoded ML/CS vocabularies (ViT, AdamW, ImageNet, learning rate,
# …) and contributed nothing on a chemistry methods paper or a physics
# simulation paper. v1.0 drops the closed-vocabulary lists. Naming is the
# LLM extractor's job — it sees the paragraph and outputs canonical names
# in the paper's actual domain.
#
# The one regex we keep is a generic "<TitleCased Name> <role-suffix>"
# matcher: phrases like "Hamiltonian objective", "PCR procedure",
# "ImageNet dataset", "Heck reaction" all match without enumerating any
# specific name. This is a heuristic FALLBACK for when LLM budget is
# exhausted; it under-recalls but doesn't over-fit to one domain.
NAMED_ROLE_SUFFIX_RE = re.compile(
    r"\b([A-Z][A-Za-z0-9-]{2,}(?:[ -][A-Z][A-Za-z0-9-]+){0,3})\s+"
    r"(method|model|scheme|algorithm|architecture|encoder|decoder|"
    r"objective|loss|function|criterion|reward|"
    r"dataset|benchmark|corpus|sample|measurement|"
    r"optimizer|solver|integrator|scheduler|"
    r"procedure|protocol|reaction|assay|"
    r"theorem|principle|assumption|"
    r"baseline|reference)\b"
)
# Generic "named parameter = value" pattern. Catches "learning rate = 1e-4",
# "temperature 0.7", "pH 7.4", "lattice size 64", "step size 0.01".
# The role-suffix list is small and domain-neutral. The leading clause
# is bounded to ≤ 3 short words to avoid grabbing sentence prefixes like
# "We set the".
HYPER_RE = re.compile(
    r"\b((?:[A-Za-z][A-Za-z-]{1,20}\s+){0,2}"
    r"(?:learning rate|batch size|lattice size|step size|"
    r"temperature|threshold|tolerance|cutoff|dropout|"
    r"weight decay|decay|ratio|fraction|depth|width|pH|"
    r"coefficient|rate|size))"
    r"\s*[:=]?\s*([0-9.eE\-]+)?",
    re.IGNORECASE,
)

_STOP_ATOM_NAMES = {
    "this", "that", "these", "those", "we", "our", "the", "their", "approach",
    "method", "model", "architecture", "encoder", "decoder", "predictive",
    "joint-embedding", "framework", "system", "module",
    "for each environment", "test environments", "test environment",
}

_PLACEHOLDER_RES = [
    re.compile(r"<\s*g\s*r\s*a\s*p\s*h\s*i\s*c\s*s\s*>"),
    re.compile(r"<\s*cit\.?\s*>"),
    re.compile(r"\\includegraphics\b[^\}]*\}"),
    re.compile(r"\\ref\{[^\}]+\}"),
]


def _scrub(text: str) -> str:
    for r in _PLACEHOLDER_RES:
        text = r.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def _is_junk_name(name: str) -> bool:
    n = name.strip()
    if len(n) > 80:
        return True
    if len(n.split()) > 10:
        return True
    if n.lower() in _STOP_ATOM_NAMES:
        return True
    letters = sum(1 for c in n if c.isalpha())
    if letters < 3:
        return True
    return False


def _ngram(name: str) -> str:
    return name.strip().lower()


def _atom_id(seq: int) -> str:
    return f"atom-{seq:03d}"


def _evidence_id(seq: int) -> str:
    return f"ev-{seq:03d}"


def _canonical_name(name: str) -> str:
    """Normalize an atom name into a stable canonical form for uid hashing.

    Lowercase, strip punctuation to spaces, collapse whitespace, remove a small
    set of structural stopwords ("the", "a", "of", "for"). Sorting the tokens
    makes 'Vision Transformer encoder' and 'encoder Vision Transformer' hash
    the same — desirable for cross-rebuild stability.
    """
    s = name.lower()
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    tokens = [t for t in s.split() if t not in {"the", "a", "an", "of", "for", "and", "or"}]
    return " ".join(sorted(tokens))


def _atom_uid(category: str, name: str, defined_by_paper_id: str) -> str:
    """Stable content-derived identifier surviving rebuilds.

    sha1 of (normalizer_version, category, canonical_name, defining_paper_id),
    truncated to 16 hex chars. The normalizer version lives in the hash so a
    future canonicalization tweak forces a clean uid namespace instead of
    silently colliding with old ids.
    """
    canonical = _canonical_name(name)
    payload = f"{ATOM_UID_NORMALIZER_VERSION}/{category}/{canonical}/{defined_by_paper_id}"
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


# Sub-categorization. v0.2 hardcoded ML-only patterns
# (encoder/decoder/attention/embedding/head and learning_rate/batch_size/
# dropout/etc.). v1.0 drops the hardcoded patterns — the LLM extractor sets
# subcategory directly when it has a clean refinement to offer (e.g.
# "integrator" under method, "pH" under parameter, "Hamiltonian" under
# objective). The heuristic path leaves subcategory = None; only LLM-set
# values land in the column. Users who want domain-specific subcategory
# heuristics can post-process the DB.
def _subcategory(category: str, name: str) -> Optional[str]:
    """v1.0: no heuristic subcategorization. Returns None.

    The LLM atom extractor still emits a subcategory field on every atom
    when it sees a clean one. That value flows through the IR into the
    DB without this function having to know any domain.
    """
    return None


def _find_defining_paper(target_pid: str, para: Paragraph, edges: list[ClassifiedEdge], category: str) -> Optional[str]:
    cand: list[tuple[str, float]] = []
    para_id = para.id
    for ce in edges:
        if ce.edge.paragraph_id != para_id:
            continue
        label, conf = best_role(ce)
        if ROLE_TO_CATEGORY.get(label) == category:
            cand.append((ce.edge.to_paper_id, conf))
    if not cand:
        return None
    cand.sort(key=lambda kv: kv[1], reverse=True)
    return cand[0][0]


def _scan_paragraph(para: Paragraph) -> list[tuple[str, str]]:
    """Domain-neutral heuristic atom scan.

    v1.0 dropped the v0.2 closed-vocabulary regexes (ViT, AdamW,
    ImageNet, …) — they hardcoded ML. We now look for a generic pattern:
    a TitleCased phrase followed by a role-suffix noun ("Hamiltonian
    objective", "ImageNet dataset", "Heck reaction", "PCR procedure").
    The role-suffix → category mapping is a small domain-neutral table.

    Recall is intentionally lower than the v0.2 ML-specific regexes; the
    LLM extractor (when budget allows) does the precise naming. This
    heuristic only fires when LLM budget is exhausted.
    """
    found: list[tuple[str, str]] = []
    text = para.text

    suffix_to_category = {
        # method / architecture / scheme / algorithm
        "method": "method", "model": "method", "scheme": "method",
        "algorithm": "method", "architecture": "method",
        "encoder": "method", "decoder": "method",
        # objective / loss / reward
        "objective": "objective", "loss": "objective",
        "function": "objective", "criterion": "objective",
        "reward": "objective",
        # data / measurements
        "dataset": "data", "benchmark": "data", "corpus": "data",
        "sample": "data", "measurement": "data",
        # procedure / solver / integrator / protocol
        "optimizer": "procedure", "solver": "procedure",
        "integrator": "procedure", "scheduler": "procedure",
        "procedure": "procedure", "protocol": "procedure",
        "reaction": "procedure", "assay": "procedure",
        # theory
        "theorem": "theory", "principle": "theory",
        "assumption": "theory",
        # baseline / reference
        "baseline": "baseline", "reference": "baseline",
    }

    for m in NAMED_ROLE_SUFFIX_RE.finditer(text):
        name = m.group(1).strip()
        suffix = m.group(2).lower().strip()
        cat = suffix_to_category.get(suffix)
        if not cat:
            continue
        if name.lower() in _STOP_ATOM_NAMES:
            continue
        label = f"{name} {suffix}".strip()
        found.append((cat, label))

    # Drop short/junk labels and stop-listed common words.
    cleaned: list[tuple[str, str]] = []
    for cat, name in found:
        normalized = name.strip()
        if not normalized or len(normalized) < 3:
            continue
        if normalized.lower() in _STOP_ATOM_NAMES:
            continue
        cleaned.append((cat, normalized))
    return cleaned


def _para_evidence(target: Paper, para: Paragraph, sec: Section, atom_id: str, ev_seq: int) -> EvidenceSpan:
    return EvidenceSpan(
        id=_evidence_id(ev_seq),
        paper_id=target.paper_id,
        section_id=sec.id,
        section_type=sec.section_type,
        verbatim_text=para.text[:1200],
        paragraph_id=para.id,
        char_start=0,
        char_end=min(len(para.text), 1200),
        supports_atom_ids=[atom_id],
    )


def _llm_extract(cfg: Config, target: Paper, paragraph_text: str) -> list[dict]:
    """Domain-neutral atom extraction prompt.

    v0.2 said "Method section" + ML-shaped categories. v1.0 explicitly
    instructs the model that the paper may be from any field, lists each
    category with cross-domain example mappings, and lets the model emit
    a free-text subcategory only when one is clearer than the top level.
    """
    from ..llm import call_llm, parse_json_object

    system = (
        "Extract implementation atoms from a paragraph of a research paper. "
        "The paper may be from any scientific or engineering field — ML, "
        "physics, chemistry, biology, economics, climate science, etc. Pick "
        "the category that best matches each atom; do NOT force ML "
        "terminology onto a non-ML paper.\n\n"
        'Return ONLY JSON: {"atoms":[{"name":"...","category":"...",'
        '"subcategory":"<optional, or null>",'
        '"description":"≤25 words"}]}.\n\n'
        f"Allowed categories: {', '.join(ATOM_CATEGORIES)}.\n"
        "Category meanings (cross-domain):\n"
        "- method: algorithmic/structural unit. ML: architecture. Physics: numerical scheme. Chemistry: synthesis route. Biology: protocol.\n"
        "- objective: function being optimized or measured. ML: loss. Physics: Hamiltonian/action. Chemistry: yield. Biology: fitness.\n"
        "- data: inputs/measurements/samples. ML: dataset. Physics: measurements. Chemistry: compounds. Biology: cohort.\n"
        "- preprocessing: transformation step on data.\n"
        "- evaluation: how outputs are judged.\n"
        "- baseline: prior method used for comparison.\n"
        "- procedure: how the method is run. ML: optimizer/scheduler. Physics: integrator/solver. Chemistry: reaction conditions. Biology: experimental procedure.\n"
        "- parameter: tunable value. ML: hyperparameter. Physics: physical constant. Chemistry: temperature/pH. Biology: read depth.\n"
        "- theory: theorem/assumption/inequality/principle.\n\n"
        "Subcategory is free-text — pick a short, domain-appropriate refinement when one helps (e.g. 'integrator' under method, 'pH' under parameter). Use null otherwise.\n"
        'If none, return {"atoms":[]}.'
    )
    result = call_llm(cfg, system, paragraph_text[:2000], model=cfg.llm.atom_model, max_tokens=400)
    if result is None:
        return []
    data = parse_json_object(result.text)
    if not data:
        return []
    return [a for a in data.get("atoms", []) if a.get("name") and a.get("category") in ATOM_CATEGORIES]


def _extract_for_paper(
    *,
    cfg: Config,
    paper: Paper,
    atoms: list[Atom],
    evidence: list[EvidenceSpan],
    seen: dict[str, str],
    ev_seq: int,
    llm_budget: int,
    edges: list[ClassifiedEdge],
    is_target: bool,
    priority_factor: float,
) -> tuple[int, int]:
    """Run heuristic + (budgeted) LLM atom extraction on one paper's method sections.

    Returns (new_llm_budget, new_ev_seq). Atoms get priority scaled by
    ``priority_factor`` so target dominates.
    """
    method_sections = [s for s in paper.sections if s.section_type == "method"]
    if not method_sections and is_target:
        method_sections = paper.sections  # fallback for target only

    for sec in method_sections:
        for para in sec.paragraphs:
            heuristics = _scan_paragraph(para)
            llm_atoms: list[dict] = []
            if llm_budget > 0 and sec.section_type == "method":
                llm_atoms = _llm_extract(cfg, paper, _scrub(para.text))
                llm_budget -= 1
            scrubbed_para = _scrub(para.text)

            # Candidates carry optional subcategory: heuristic path leaves
            # it None; LLM may set it to a short free-text refinement.
            candidates: list[tuple[str, str, str, Optional[str]]] = []
            for cat, name in heuristics:
                if _is_junk_name(name):
                    continue
                candidates.append((cat, name, scrubbed_para[:240], None))
            for la in llm_atoms:
                name = (la.get("name") or "").strip()
                cat = la.get("category")
                desc = (la.get("description") or scrubbed_para[:240]).strip()
                sub = la.get("subcategory")
                if isinstance(sub, str):
                    sub = sub.strip() or None
                else:
                    sub = None
                if _is_junk_name(name) or not cat:
                    continue
                candidates.append((cat, name, desc, sub))

            for category, name, description, sub in candidates:
                key = f"{category}:{_ngram(name)}"
                if key in seen:
                    atom = next(a for a in atoms if a.id == seen[key])
                    if paper.paper_id not in atom.used_by_paper_ids:
                        atom.used_by_paper_ids.append(paper.paper_id)
                    if len(description) > len(atom.description):
                        atom.description = description
                    if sub and not atom.subcategory:
                        atom.subcategory = sub
                    continue
                defining = (
                    _find_defining_paper(paper.paper_id, para, edges, category)
                    or paper.paper_id
                )
                atom_id = _atom_id(len(atoms) + 1)
                uid = _atom_uid(category, name, defining)
                seen[key] = atom_id
                ev_seq += 1
                ev = _para_evidence(paper, para, sec, atom_id, ev_seq)
                ev.verbatim_text = _scrub(ev.verbatim_text)
                evidence.append(ev)
                atoms.append(
                    Atom(
                        id=atom_id,
                        uid=uid,
                        name=name,
                        category=category,
                        subcategory=sub,
                        defined_by_paper_id=defining,
                        used_by_paper_ids=[paper.paper_id],
                        description=description[:300],
                        evidence_span_ids=[ev.id],
                        priority=priority_factor,
                    )
                )
    return llm_budget, ev_seq


def _allocate_atom_budget(
    target: Paper,
    parsed_papers: list,
    edges: list[ClassifiedEdge],
    total: int,
    *,
    target_share: float = 0.4,
    per_paper_cap: int = 10,
    load_bearing_threshold: float = 0.3,
    min_call_per_load_bearing: int = 1,
) -> dict[str, int]:
    """Distribute ``cfg.compile.atom_llm_max_calls`` across parsed papers.

    v0.2 ran full LLM extraction on the target plus ``atom_paper_count``
    top-cited papers (default 10), leaving 88% of the neighborhood
    untouched. v1.0 allocates by edge weight so every paper above a
    threshold receives at least one LLM call, while low-signal papers
    fall back to heuristic-only extraction (zero LLM cost).

    Target reserves ``target_share`` of the total budget (min 20 calls).
    Remaining budget splits across cited papers proportional to the sum of
    their incoming edge weights from the target. Each "load-bearing" paper
    (incoming weight ≥ ``load_bearing_threshold``) is guaranteed at least
    ``min_call_per_load_bearing`` call so a single very-high-weight paper
    can't starve smaller-weight but still-relevant papers.

    Papers absent from the returned dict still get heuristic extraction
    in the caller (budget=0). They contribute atoms via regex hits only.
    """
    target_budget = min(total, max(20, int(total * target_share)))
    out: dict[str, int] = {target.paper_id: target_budget}
    remaining = max(0, total - target_budget)
    if remaining <= 0:
        return out

    # Sum incoming weights per cited paper, restricted to those we have
    # parsed text for (extraction on metadata-only papers yields zero atoms).
    parsed_pids = {np.paper_id for np in parsed_papers if np.parsed is not None}
    weights_by_pid: dict[str, float] = {}
    for ce in edges:
        if ce.weight is None or ce.weight <= 0:
            continue
        pid = ce.edge.to_paper_id
        if pid not in parsed_pids:
            continue
        weights_by_pid[pid] = weights_by_pid.get(pid, 0.0) + ce.weight

    if not weights_by_pid:
        return out

    total_w = sum(weights_by_pid.values())
    proposed: dict[str, int] = {}
    for pid, w in sorted(weights_by_pid.items(), key=lambda kv: -kv[1]):
        share = int(round(remaining * w / total_w))
        share = min(per_paper_cap, share)
        if w >= load_bearing_threshold and share < min_call_per_load_bearing:
            share = min_call_per_load_bearing
        if share > 0:
            proposed[pid] = share

    # Constrain total to ≤ remaining. Trim from the smallest allocations first.
    used = sum(proposed.values())
    if used > remaining:
        # Sort by share ascending and trim until we fit.
        for pid in sorted(proposed, key=lambda p: proposed[p]):
            if used <= remaining:
                break
            cut = min(proposed[pid], used - remaining)
            proposed[pid] -= cut
            used -= cut
        proposed = {pid: s for pid, s in proposed.items() if s > 0}

    out.update(proposed)
    return out


async def extract_atoms(
    cfg: Config,
    target: Paper,
    neighborhood: Neighborhood,
    edges: list[ClassifiedEdge],
) -> tuple[list[Atom], list[EvidenceSpan]]:
    atoms: list[Atom] = []
    evidence: list[EvidenceSpan] = []
    seen: dict[str, str] = {}
    ev_seq = 0
    total_budget = cfg.compile.atom_llm_max_calls

    # Phase 5: every parsed paper gets a budget. Allocator weights papers by
    # incoming edge weight (Phase 4) so high-signal papers get real LLM
    # extraction while low-signal papers fall back to heuristic-only.
    parsed_papers = [
        np for np in neighborhood.papers.values()
        if np.parsed is not None and np.depth <= 2
    ]
    allocation = _allocate_atom_budget(target, parsed_papers, edges, total_budget)
    n_lb = sum(1 for v in allocation.values() if v > 0)
    print(
        f"atom budget: total={total_budget}, target={allocation.get(target.paper_id, 0)}, "
        f"papers_with_llm_calls={n_lb}, papers_heuristic_only={len(parsed_papers) + 1 - n_lb}",
        file=sys.stderr,
    )

    # ---- target paper: largest allocated share, full extraction ----
    target_budget = allocation.get(target.paper_id, total_budget)
    _, ev_seq = _extract_for_paper(
        cfg=cfg,
        paper=target,
        atoms=atoms,
        evidence=evidence,
        seen=seen,
        ev_seq=ev_seq,
        llm_budget=target_budget,
        edges=edges,
        is_target=True,
        priority_factor=1.0,
    )

    # ---- all parsed cited papers: each gets its allocated budget ----
    # Low-budget papers (allocation == 0) still receive heuristic extraction;
    # they contribute regex-matched atoms (named losses, optimizers, datasets,
    # known-list datasets) without burning LLM calls. This is what fixes the
    # 88% zero-atom-paper problem from the audit.
    parsed_sorted = sorted(parsed_papers, key=lambda np: -np.priority)
    for np in parsed_sorted:
        paper_budget = allocation.get(np.paper_id, 0)
        # priority_factor scales the recorded atom.priority (used at retrieval),
        # not the LLM budget. Keep the v0.2 0.6 multiplier for non-target atoms.
        _, ev_seq = _extract_for_paper(
            cfg=cfg,
            paper=np.parsed,
            atoms=atoms,
            evidence=evidence,
            seen=seen,
            ev_seq=ev_seq,
            llm_budget=paper_budget,
            edges=edges,
            is_target=False,
            priority_factor=0.6,
        )

    # Atoms harvested from experiments/results sections via classified
    # citation edges. The set below is the "evaluation-time evidence"
    # category set; works across domains because data/evaluation/baseline
    # are universal scientific concepts (ML datasets, physics measurements,
    # chemistry test sets, biology cohorts — all "data").
    for sec in target.sections:
        if sec.section_type not in {"experiments", "results"}:
            continue
        for para in sec.paragraphs:
            for ce in edges:
                if ce.edge.paragraph_id != para.id:
                    continue
                label, _ = best_role(ce)
                cat = ROLE_TO_CATEGORY.get(label)
                if cat not in {"data", "evaluation", "baseline"}:
                    continue
                neighbor = neighborhood.papers.get(ce.edge.to_paper_id)
                neighbor_title = (neighbor.record.get("title") if neighbor and neighbor.record else "") or ce.edge.to_paper_id
                key = f"{cat}:{_ngram(neighbor_title)}"
                if key in seen:
                    continue
                atom_id = _atom_id(len(atoms) + 1)
                uid = _atom_uid(cat, neighbor_title, ce.edge.to_paper_id)
                seen[key] = atom_id
                ev_seq += 1
                ev = _para_evidence(target, para, sec, atom_id, ev_seq)
                ev.verbatim_text = _scrub(ev.verbatim_text)
                evidence.append(ev)
                atoms.append(
                    Atom(
                        id=atom_id,
                        uid=uid,
                        name=neighbor_title,
                        category=cat,
                        subcategory=None,  # neighbor-title atoms have no LLM-supplied refinement
                        defined_by_paper_id=ce.edge.to_paper_id,
                        used_by_paper_ids=[target.paper_id],
                        description=_scrub(para.text)[:240],
                        evidence_span_ids=[ev.id],
                        priority=0.8,
                    )
                )

    return atoms, evidence


def collect_missing_details(target: Paper, atoms: list[Atom]) -> list[MissingDetail]:
    gaps: list[MissingDetail] = []
    seen: set[str] = set()
    text = " ".join(p.text for s in target.sections for p in s.paragraphs)

    for m in HYPER_RE.finditer(text):
        name = (m.group(1) or "").strip().lower()
        val = m.group(2)
        if val:
            continue
        if not name or name in seen:
            continue
        seen.add(name)
        gaps.append(
            MissingDetail(
                id=f"md-{len(gaps) + 1:03d}",
                question=f"{name} not explicitly stated.",
                category="parameter",
                options=[],
                rationale="Mentioned without a value; suggested default required.",
            )
        )

    cats_present = {a.category for a in atoms}
    # v1.0: every paper, regardless of domain, should declare its
    # objective, data, evaluation protocol, and procedure. If any of
    # these is absent from the extracted atoms, that's a flag for the
    # user to review — not a hard error.
    for need in ("objective", "procedure", "data", "evaluation"):
        if need not in cats_present:
            gaps.append(
                MissingDetail(
                    id=f"md-{len(gaps) + 1:03d}",
                    question=f"No {need} atom extracted from method/experiments sections.",
                    category=need,
                    options=[],
                    rationale="Compiler did not find a citation or named entity for this category. Manual review needed.",
                )
            )
    return gaps
