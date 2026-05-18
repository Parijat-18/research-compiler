from __future__ import annotations

import json
import re
import sys
from typing import Optional

from ..classify.edge import ClassifiedEdge, best_role
from ..config import Config
from ..expand import Neighborhood
from ..ir import Paper, Paragraph, Section
from . import ATOM_CATEGORIES, Atom, EvidenceSpan, MissingDetail

ROLE_TO_CATEGORY = {
    "architecture_dependency": "architecture",
    "loss_function_dependency": "loss",
    "dataset_dependency": "dataset",
    "preprocessing_dependency": "preprocessing",
    "evaluation_protocol_dependency": "evaluation",
    "baseline_dependency": "baseline",
    "optimizer_or_training_trick": "optimizer",
    "theoretical_assumption": "architecture",
}

NAMED_LOSS_RE = re.compile(r"\b(InfoNCE|MSE|MAE|KL|GAN|VICReg|SIGReg|Barlow Twins|cross[- ]entropy|contrastive|hinge|triplet|focal|Dice|Tversky|Huber|Wasserstein)\s+(loss|objective|criterion)?\b", re.IGNORECASE)
NAMED_ARCH_RE = re.compile(r"\b((?:ViT|ResNet|DenseNet|EfficientNet|U-Net|Transformer|BERT|GPT|T5|CLIP|DINO|MAE|JEPA|I-JEPA|V-JEPA|LeWorldModel|LeWM|MLP|CNN|RNN|LSTM|GRU|Swin|ConvNeXt)(?:[- ][A-Za-z0-9]+)*)\s+(encoder|decoder|backbone|block|module|attention|transformer|network|head|architecture)?\b")
# Datasets: a known-list OR an explicit "<Name> dataset|benchmark|corpus" phrase
NAMED_DATASET_KNOWN_RE = re.compile(r"\b(ImageNet|COCO|CIFAR(?:[- ]?\d+)?|WikiText(?:[- ]?\d+)?|C4|The Pile|OpenWebText|LAION(?:[- ]?\d+[A-Z]?)?|RoboNet|Ego4D|DAVIS|MS COCO|Pascal VOC|Atari|MuJoCo|DM Control|Meta-World)\b")
NAMED_DATASET_PHRASE_RE = re.compile(r"\b([A-Z][A-Za-z0-9]{1,}(?:[- ][A-Z]?[A-Za-z0-9]+){0,2})\s+(dataset|benchmark|corpus|environment|simulator)\b")
NAMED_OPT_RE = re.compile(r"\b(AdamW?|SGD|Lion|Lamb|RMSProp|Adafactor|LARS|LAMB)\b")
HYPER_RE = re.compile(r"(learning rate|lr|batch size|warmup steps?|temperature|dropout|weight decay)\s*[:=]?\s*([0-9.eE\-]+)?", re.IGNORECASE)

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
    found: list[tuple[str, str]] = []
    text = para.text

    for m in NAMED_LOSS_RE.finditer(text):
        anchor = m.group(1).strip()
        suffix = m.group(2) or "loss"
        found.append(("loss", f"{anchor} {suffix}".strip()))

    for m in NAMED_ARCH_RE.finditer(text):
        name = m.group(1).strip()
        suffix = m.group(2)
        label = f"{name} {suffix}".strip() if suffix else name
        found.append(("architecture", label))

    for m in NAMED_OPT_RE.finditer(text):
        found.append(("optimizer", m.group(0)))

    for m in NAMED_DATASET_KNOWN_RE.finditer(text):
        found.append(("dataset", m.group(0).strip()))

    for m in NAMED_DATASET_PHRASE_RE.finditer(text):
        name = f"{m.group(1)} {m.group(2)}".strip()
        if m.group(1).lower() in _STOP_ATOM_NAMES:
            continue
        found.append(("dataset", name))

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
        supports_atom_ids=[atom_id],
    )


def _llm_extract(cfg: Config, target: Paper, paragraph_text: str) -> list[dict]:
    from ..llm import call_llm, parse_json_object

    system = (
        "Extract implementation atoms from a paragraph of a research paper's Method section. "
        "Return JSON: {\"atoms\":[{\"name\":\"...\",\"category\":\"...\",\"description\":\"≤25 words\"}]}. "
        f"Allowed categories: {', '.join(ATOM_CATEGORIES)}. If none, return {{\"atoms\":[]}}."
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

            candidates: list[tuple[str, str, str]] = []
            for cat, name in heuristics:
                if _is_junk_name(name):
                    continue
                candidates.append((cat, name, scrubbed_para[:240]))
            for la in llm_atoms:
                name = (la.get("name") or "").strip()
                cat = la.get("category")
                desc = (la.get("description") or scrubbed_para[:240]).strip()
                if _is_junk_name(name) or not cat:
                    continue
                candidates.append((cat, name, desc))

            for category, name, description in candidates:
                key = f"{category}:{_ngram(name)}"
                if key in seen:
                    atom = next(a for a in atoms if a.id == seen[key])
                    if paper.paper_id not in atom.used_by_paper_ids:
                        atom.used_by_paper_ids.append(paper.paper_id)
                    if len(description) > len(atom.description):
                        atom.description = description
                    continue
                defining = (
                    _find_defining_paper(paper.paper_id, para, edges, category)
                    or paper.paper_id
                )
                atom_id = _atom_id(len(atoms) + 1)
                seen[key] = atom_id
                ev_seq += 1
                ev = _para_evidence(paper, para, sec, atom_id, ev_seq)
                ev.verbatim_text = _scrub(ev.verbatim_text)
                evidence.append(ev)
                atoms.append(
                    Atom(
                        id=atom_id,
                        name=name,
                        category=category,
                        defined_by_paper_id=defining,
                        used_by_paper_ids=[paper.paper_id],
                        description=description[:300],
                        evidence_span_ids=[ev.id],
                        priority=priority_factor,
                    )
                )
    return llm_budget, ev_seq


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
    llm_budget = cfg.compile.atom_llm_max_calls

    # ---- target paper: full extraction (heuristic + LLM, priority 1.0) ----
    llm_budget, ev_seq = _extract_for_paper(
        cfg=cfg,
        paper=target,
        atoms=atoms,
        evidence=evidence,
        seen=seen,
        ev_seq=ev_seq,
        llm_budget=llm_budget,
        edges=edges,
        is_target=True,
        priority_factor=1.0,
    )

    # ---- top-K acquired cited papers: lighter extraction ----
    # Why: foundational components (InfoNCE, AdamW, ViT, …) are defined in cited
    # papers. Extracting from their method sections recovers atoms whose defining
    # paper isn't the target. Lower priority so target atoms still dominate.
    cited_with_text = sorted(
        [np for np in neighborhood.papers.values() if np.parsed is not None and np.depth <= 2],
        key=lambda np: -np.priority,
    )
    atom_paper_budget = getattr(cfg.compile, "atom_paper_count", 10)
    top_cited = cited_with_text[:atom_paper_budget]
    for np in top_cited:
        if llm_budget <= 0:
            break
        llm_budget, ev_seq = _extract_for_paper(
            cfg=cfg,
            paper=np.parsed,
            atoms=atoms,
            evidence=evidence,
            seen=seen,
            ev_seq=ev_seq,
            llm_budget=llm_budget,
            edges=edges,
            is_target=False,
            priority_factor=0.6,
        )

    # eval/baseline atoms from experiments sections
    for sec in target.sections:
        if sec.section_type not in {"experiments", "results"}:
            continue
        for para in sec.paragraphs:
            for ce in edges:
                if ce.edge.paragraph_id != para.id:
                    continue
                label, _ = best_role(ce)
                cat = ROLE_TO_CATEGORY.get(label)
                if cat not in {"dataset", "evaluation", "baseline"}:
                    continue
                neighbor = neighborhood.papers.get(ce.edge.to_paper_id)
                neighbor_title = (neighbor.record.get("title") if neighbor and neighbor.record else "") or ce.edge.to_paper_id
                key = f"{cat}:{_ngram(neighbor_title)}"
                if key in seen:
                    continue
                atom_id = _atom_id(len(atoms) + 1)
                seen[key] = atom_id
                ev_seq += 1
                ev = _para_evidence(target, para, sec, atom_id, ev_seq)
                ev.verbatim_text = _scrub(ev.verbatim_text)
                evidence.append(ev)
                atoms.append(
                    Atom(
                        id=atom_id,
                        name=neighbor_title,
                        category=cat,
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
        name = m.group(1).lower()
        val = m.group(2)
        if val:
            continue
        if name in seen:
            continue
        seen.add(name)
        gaps.append(
            MissingDetail(
                id=f"md-{len(gaps) + 1:03d}",
                question=f"{name} not explicitly stated.",
                category="hyperparameter",
                options=[],
                rationale="Mentioned without a value; suggested default required.",
            )
        )

    cats_present = {a.category for a in atoms}
    for need in ("loss", "optimizer", "dataset", "evaluation"):
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
