from dataclasses import dataclass, field
from typing import Optional

ATOM_CATEGORIES = (
    # v1.0: domain-neutral labels so the plugin works for ML, physics,
    # chemistry, biology, economics — any field with implementable
    # methods. Mapping from common domains:
    #   method        ML: architecture       physics: numerical scheme
    #                 chem: synthesis route   bio: protocol
    #   objective     ML: loss function      physics: action / Hamiltonian
    #                 chem: yield target     bio: fitness function
    #   data          ML: dataset            physics: measurements
    #                 chem: compound set     bio: samples / sequences
    #   preprocessing ML: tokenizer/augment  physics: filter / detrend
    #   evaluation    ML: accuracy/F1        physics: convergence diag
    #                 chem: NMR/MS verify    bio: cross-validation
    #   baseline      comparison reference (works in any field)
    #   procedure     ML: optimizer/sched    physics: integrator/solver
    #                 chem: reaction proto   bio: experimental procedure
    #   parameter     ML: hyperparameter     physics: physical constant
    #                 chem: temperature/pH   bio: read depth
    #   theory        assumption / theorem / inequality (any field)
    "method",
    "objective",
    "data",
    "preprocessing",
    "evaluation",
    "baseline",
    "procedure",
    "parameter",
    "theory",
)


@dataclass
class Atom:
    id: str
    name: str
    category: str
    defined_by_paper_id: str
    # Content-stable identifier — sha1(category, canonical_name, defined_by_paper_id)[:16].
    # Survives rebuilds; the join key everywhere except human display.
    uid: str = ""
    # v1.0: optional free-text refinement set by the LLM extractor (or by
    # a domain-specific config preset). Examples: a "method" atom in an
    # ML paper might carry subcategory="encoder"; in a physics paper,
    # subcategory="integrator". Never hardcoded — the LLM picks the label.
    # Indexed in the DB so callers can filter on it when present.
    subcategory: Optional[str] = None
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
    # paragraph_id resolves to a chunk_id at ingest time. Without it the
    # atom_evidence.chunk_id column cannot be populated.
    paragraph_id: Optional[str] = None
    char_start: Optional[int] = None
    char_end: Optional[int] = None
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
