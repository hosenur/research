from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_serializer


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


class TextNode(ApiModel):
    type: Literal["text"] = "text"
    text: str


class CitationNode(ApiModel):
    type: Literal["citation"] = "citation"
    raw_text: str
    reference_ids: list[str]
    unresolved_fragments: list[str] = Field(default_factory=list)


ParagraphNode = TextNode | CitationNode


class Paragraph(ApiModel):
    id: str
    nodes: list[ParagraphNode]


class Section(ApiModel):
    id: str
    title: str
    number: str | None = None
    paragraphs: list[Paragraph]


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


class Paper(ApiModel):
    title: str
    abstract: str | None = None
    authors: list[CSLName] = Field(default_factory=list)
    year: int | None = None
    identifiers: dict[str, str] = Field(default_factory=dict)
    citation_style: str | None = None
    sections: list[Section]
    references: list[Reference]
    unresolved_reference_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
