from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_serializer, model_validator


def to_camel(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(part.capitalize() for part in rest)


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class CompactCSLModel(ApiModel):
    @model_serializer(mode="wrap")
    def omit_empty_fields(self, handler: Any) -> dict[str, Any]:
        serialized = handler(self)
        return {
            key: value
            for key, value in serialized.items()
            if value is not None and value != []
        }


class BoundingBox(ApiModel):
    """One GROBID coordinate box in PDF points."""

    page: int = Field(ge=1)
    x: float
    y: float
    width: float = Field(ge=0)
    height: float = Field(ge=0)


class ExtractionPointer(ApiModel):
    """Traceability from a normalized node back to GROBID TEI and the PDF."""

    grobid_id: str | None = None
    coordinates: list[BoundingBox] = Field(default_factory=list)


class SentenceSpan(ApiModel):
    """Half-open sentence offsets in the normalized paragraph projection."""

    id: str
    start_offset: int = Field(ge=0)
    end_offset: int = Field(ge=0)
    source: ExtractionPointer | None = None

    @model_validator(mode="after")
    def validate_range(self) -> "SentenceSpan":
        if self.end_offset < self.start_offset:
            raise ValueError("Sentence endOffset must be at or after startOffset.")
        return self


class PdfPreflightReport(ApiModel):
    page_count: int | None = Field(default=None, ge=0)
    selectable_text_characters: int = Field(default=0, ge=0)
    sampled_pages: int = Field(default=0, ge=0)
    encrypted: bool = False
    ocr_recommended: bool = False
    warnings: list[str] = Field(default_factory=list)


class ExtractionQualityReport(ApiModel):
    status: Literal["usable", "warning", "unusable"]
    body_characters: int = Field(ge=0)
    section_count: int = Field(ge=0)
    sentence_count: int = Field(ge=0)
    citation_count: int = Field(ge=0)
    reference_count: int = Field(ge=0)
    parsed_reference_count: int = Field(ge=0)
    resolved_target_ratio: float = Field(ge=0, le=1)
    warnings: list[str] = Field(default_factory=list)


class ExtractionMetadata(ApiModel):
    provider: Literal["grobid"] = "grobid"
    grobid_version: str | None = None
    processed_at: str
    duration_ms: int = Field(ge=0)
    pdf_sha256: str
    tei_sha256: str
    tei_artifact_id: str | None = None
    request_options: dict[str, Any] = Field(default_factory=dict)
    preflight: PdfPreflightReport
    quality: ExtractionQualityReport
    ocr_applied: bool = False
    recovery_steps: list[str] = Field(default_factory=list)


class TextNode(ApiModel):
    type: Literal["text"] = "text"
    text: str


CitationResolutionMethod = Literal[
    "grobid-target",
    "numeric-fallback",
    "author-year-fallback",
    "harvard-key-fallback",
    "manual",
    "legacy",
    "none",
]
CitationConfidence = Literal["high", "medium", "low"]
CitationResolutionStatus = Literal["resolved", "partial", "ambiguous", "unresolved"]
CitationForm = Literal["numeric", "parenthetical", "narrative", "note", "unknown"]
CitationStyleFamily = Literal[
    "numeric",
    "author-year",
    "author-page",
    "harvard-key",
    "mixed",
    "unknown",
]
CitationStyleConfidence = Literal["high", "medium", "low"]


class CSLStyleCandidate(ApiModel):
    """A plausible rendering style, never an asserted exact match."""

    id: str
    label: str
    score: float = Field(ge=0, le=1)
    reason: str


class CitationStyleDetection(ApiModel):
    """Evidence-backed style-family classification from the parsed paper."""

    family: CitationStyleFamily
    syntaxes: list[str] = Field(default_factory=list)
    confidence: CitationStyleConfidence
    csl_candidates: list[CSLStyleCandidate] = Field(default_factory=list)
    needs_confirmation: bool = True
    evidence: dict[str, int] = Field(default_factory=dict)
    reasons: list[str] = Field(default_factory=list)


class CitationItem(ApiModel):
    """One source inside an in-text citation cluster."""

    source_id: str = Field(min_length=1)
    prefix: str | None = None
    suffix: str | None = None
    locator: str | None = None
    label: str | None = None
    suppress_author: bool = False
    author_only: bool = False
    resolution_method: CitationResolutionMethod = "none"
    confidence: CitationConfidence = "low"


class CitationAnchor(ApiModel):
    """Half-open offsets into the paragraph's normalized plain-text projection."""

    paragraph_id: str = Field(min_length=1)
    start_offset: int = Field(ge=0)
    end_offset: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_range(self) -> "CitationAnchor":
        if self.end_offset < self.start_offset:
            raise ValueError("Citation anchor endOffset must be at or after startOffset.")
        return self


class CitationResolution(ApiModel):
    status: CitationResolutionStatus
    confidence: CitationConfidence
    methods: list[CitationResolutionMethod] = Field(default_factory=list)
    candidate_source_ids: list[str] = Field(default_factory=list)
    unresolved_source_ids: list[str] = Field(default_factory=list)


class CitationNode(ApiModel):
    """A stable, source-linked occurrence of a citation in the manuscript."""

    type: Literal["citation"] = "citation"
    id: str | None = None
    raw_text: str
    items: list[CitationItem] = Field(default_factory=list)
    anchor: CitationAnchor | None = None
    form: CitationForm = "unknown"
    resolution: CitationResolution = Field(
        default_factory=lambda: CitationResolution(
            status="unresolved",
            confidence="low",
            methods=["none"],
        )
    )
    unresolved_fragments: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    source_spans: list[ExtractionPointer] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_reference_ids(cls, value: Any) -> Any:
        """Accept older Paper JSON while emitting only the canonical item model."""
        if not isinstance(value, dict) or "items" in value:
            return value
        reference_ids = value.get("referenceIds", value.get("reference_ids"))
        if not isinstance(reference_ids, list):
            return value

        migrated = dict(value)
        migrated.pop("referenceIds", None)
        migrated.pop("reference_ids", None)
        migrated["items"] = [
            {
                "sourceId": reference_id,
                "resolutionMethod": "legacy",
                "confidence": "medium",
            }
            for reference_id in reference_ids
            if isinstance(reference_id, str) and reference_id
        ]
        if "resolution" not in migrated:
            migrated["resolution"] = {
                "status": "resolved" if migrated["items"] else "unresolved",
                "confidence": "medium" if migrated["items"] else "low",
                "methods": ["legacy"] if migrated["items"] else ["none"],
            }
        return migrated

    @property
    def source_ids(self) -> list[str]:
        return list(dict.fromkeys(item.source_id for item in self.items))

    @property
    def reference_ids(self) -> list[str]:
        """Compatibility accessor for internal callers migrating to ``source_ids``."""
        return self.source_ids


ParagraphNode = TextNode | CitationNode


class Paragraph(ApiModel):
    id: str
    nodes: list[ParagraphNode]
    sentences: list[SentenceSpan] = Field(default_factory=list)
    source: ExtractionPointer | None = None


class Section(ApiModel):
    id: str
    title: str
    number: str | None = None
    paragraphs: list[Paragraph]
    source: ExtractionPointer | None = None


class CSLName(CompactCSLModel):
    given: str | None = None
    family: str | None = None
    literal: str | None = None


class CSLDate(CompactCSLModel):
    date_parts: list[list[int]] = Field(alias="date-parts")


class CSLItem(CompactCSLModel):
    id: str
    type: str
    title: str | None = None
    author: list[CSLName] = Field(default_factory=list)
    issued: CSLDate | None = None
    container_title: str | None = Field(default=None, alias="container-title")
    volume: str | None = None
    issue: str | None = None
    page: str | None = None
    publisher: str | None = None
    publisher_place: str | None = Field(default=None, alias="publisher-place")
    doi: str | None = Field(default=None, alias="DOI")
    url: str | None = Field(default=None, alias="URL")
    isbn: str | None = Field(default=None, alias="ISBN")
    issn: str | None = Field(default=None, alias="ISSN")
    pmid: str | None = Field(default=None, alias="PMID")
    pmcid: str | None = Field(default=None, alias="PMCID")
    archive: str | None = None
    archive_location: str | None = Field(default=None, alias="archive_location")


class OpenAlexWork(ApiModel):
    id: str
    doi: str | None = None
    title: str | None = None
    year: int | None = None
    abstract: str | None = None
    cited_by_count: int | None = None
    landing_page_url: str | None = None
    match_method: Literal["doi", "arxiv", "title", "search"]
    confidence: Literal["high", "medium"]


class ClaimQuery(ApiModel):
    section_id: str
    section_title: str
    text: str
    status: Literal["searched", "empty", "error"] = "searched"
    error: str | None = None


class MissingWorkFinding(ApiModel):
    section_id: str
    section_title: str
    claim: str
    work: OpenAlexWork
    reason: str


class MissingWorkReport(ApiModel):
    queries: list[ClaimQuery] = Field(default_factory=list)
    findings: list[MissingWorkFinding] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class Reference(ApiModel):
    id: str
    raw_text: str
    csl: CSLItem | None
    status: Literal["parsed", "partial", "failed"]
    raw_fields: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    openalex: OpenAlexWork | None = None
    openalex_status: Literal["matched", "unmatched", "error", "skipped"] | None = None
    openalex_error: str | None = None
    source: ExtractionPointer | None = None


class Paper(ApiModel):
    title: str
    abstract: str | None = None
    authors: list[CSLName] = Field(default_factory=list)
    year: int | None = None
    identifiers: dict[str, str] = Field(default_factory=dict)
    citation_style: str | None = None
    citation_style_detection: CitationStyleDetection | None = None
    sections: list[Section]
    references: list[Reference]
    extraction: ExtractionMetadata | None = None
    unresolved_reference_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
