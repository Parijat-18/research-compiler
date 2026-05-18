from dataclasses import dataclass, field
from typing import Optional

ATOM_CATEGORIES = (
    "architecture",
    "loss",
    "dataset",
    "preprocessing",
    "evaluation",
    "baseline",
    "optimizer",
    "hyperparameter",
    "training_trick",
)


@dataclass
class Atom:
    id: str
    name: str
    category: str
    defined_by_paper_id: str
    used_by_paper_ids: list[str] = field(default_factory=list)
    description: str = ""
    evidence_span_ids: list[str] = field(default_factory=list)
    equation_refs: list[dict] = field(default_factory=list)
    priority: float = 0.0
    dependencies: list[str] = field(default_factory=list)


@dataclass
class EvidenceSpan:
    id: str
    paper_id: str
    section_id: Optional[str]
    section_type: str
    verbatim_text: str
    char_range: Optional[tuple[int, int]] = None
    supports_atom_ids: list[str] = field(default_factory=list)


@dataclass
class MissingDetail:
    id: str
    question: str
    category: str
    options: list[str] = field(default_factory=list)
    suggested_default: Optional[str] = None
    rationale: str = ""
