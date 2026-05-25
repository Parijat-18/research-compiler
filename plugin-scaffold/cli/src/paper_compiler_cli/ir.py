from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

SCHEMA_VERSION = "1.0"

SectionType = Literal[
    "abstract",
    "introduction",
    "related_work",
    "method",
    "experiments",
    "results",
    "discussion",
    "conclusion",
    "appendix",
    "other",
]


class Author(BaseModel):
    name: str
    s2_author_id: Optional[str] = None


class Metadata(BaseModel):
    title: str
    authors: list[Author] = Field(default_factory=list)
    year: Optional[int] = None
    venue: Optional[str] = None
    abstract: Optional[str] = None


class ExternalIds(BaseModel):
    arxiv: Optional[str] = None
    doi: Optional[str] = None
    corpus_id: Optional[str] = None


class Acquisition(BaseModel):
    # Open-ended in v1.0: any source name registered in ``sources/`` may
    # appear here (e.g. ``openalex_pdf``, ``unpaywall_pdf``, ``crossref_pdf``).
    # The closed Literal of v0.2 was too narrow once the registry landed.
    source: str
    fetched_at: str
    cache_path: Optional[str] = None


class Citation(BaseModel):
    marker: str
    ref_id: str
    resolved_paper_id: Optional[str] = None
    context_window: str = ""


class Paragraph(BaseModel):
    id: str
    text: str
    citations: list[Citation] = Field(default_factory=list)
    equation_refs: list[str] = Field(default_factory=list)
    algorithm_refs: list[str] = Field(default_factory=list)
    table_refs: list[str] = Field(default_factory=list)
    figure_refs: list[str] = Field(default_factory=list)


class Section(BaseModel):
    id: str
    title: str
    level: int = 1
    section_type: SectionType = "other"
    paragraphs: list[Paragraph] = Field(default_factory=list)


class Equation(BaseModel):
    id: str
    latex: str
    section_id: Optional[str] = None
    mentioned_in: list[str] = Field(default_factory=list)


class Algorithm(BaseModel):
    id: str
    title: Optional[str] = None
    pseudocode: str
    section_id: Optional[str] = None


class Table(BaseModel):
    id: str
    caption: str = ""
    section_id: Optional[str] = None
    rows: Optional[list[list[str]]] = None


class Figure(BaseModel):
    id: str
    caption: str = ""
    section_id: Optional[str] = None


class Reference(BaseModel):
    ref_id: str
    marker: str
    raw: str
    resolved_paper_id: Optional[str] = None
    resolution_confidence: float = 0.0


class Paper(BaseModel):
    schema_version: str = SCHEMA_VERSION
    paper_id: str
    external_ids: ExternalIds = Field(default_factory=ExternalIds)
    metadata: Metadata
    acquisition: Optional[Acquisition] = None
    sections: list[Section] = Field(default_factory=list)
    equations: list[Equation] = Field(default_factory=list)
    algorithms: list[Algorithm] = Field(default_factory=list)
    tables: list[Table] = Field(default_factory=list)
    figures: list[Figure] = Field(default_factory=list)
    references: list[Reference] = Field(default_factory=list)


_SECTION_TITLE_RULES: list[tuple[SectionType, tuple[str, ...]]] = [
    ("abstract", ("abstract",)),
    ("introduction", ("introduction", "intro")),
    ("related_work", ("related work", "background", "prior work", "literature")),
    ("method", ("method", "approach", "model", "architecture", "framework", "system")),
    ("experiments", ("experiment", "setup", "training details", "implementation details")),
    ("results", ("result", "evaluation", "benchmark", "analysis")),
    ("discussion", ("discussion",)),
    ("conclusion", ("conclusion", "summary")),
    ("appendix", ("appendix", "supplementary")),
]


def classify_section_title(title: str) -> SectionType:
    t = title.strip().lower()
    for label, needles in _SECTION_TITLE_RULES:
        for n in needles:
            if n in t:
                return label
    return "other"
