from __future__ import annotations

import asyncio
import hashlib
import time
from datetime import UTC, datetime
from xml.etree import ElementTree as ET

from app.config import MAX_PDF_SIZE, MAX_TEI_SIZE
from app.exceptions import (
    FileTooLargeError,
    GrobidNoTextError,
    GrobidRequestError,
    GrobidUnavailableError,
    InvalidDocumentError,
    UnsupportedMediaTypeError,
)
from app.repositories.artifacts import ExtractionArtifactStore
from app.repositories.grobid import GrobidRepository, GrobidResult
from app.schemas.paper import (
    CitationNode,
    ExtractionMetadata,
    ExtractionQualityReport,
    Paper,
    PdfPreflightReport,
    TextNode,
)
from app.services.pdf_preflight import PdfPreflightService
from app.services.tei_parser import NS, TEI_NAMESPACE, TEIParseError, parse_tei, qname


class PaperService:
    """Orchestrate PDF preflight → optional OCR → GROBID → quality-gated Paper."""

    def __init__(
        self,
        grobid: GrobidRepository,
        preflight: PdfPreflightService,
        artifacts: ExtractionArtifactStore,
        *,
        ocr_enabled: bool,
        fallback_flavor: str | None,
    ) -> None:
        self._grobid = grobid
        self._preflight = preflight
        self._artifacts = artifacts
        self._ocr_enabled = ocr_enabled
        self._fallback_flavor = fallback_flavor

    async def parse_pdf(self, content: bytes, filename: str) -> Paper:
        started = time.perf_counter()
        original_pdf = validate_pdf(content)
        pdf_sha256 = hashlib.sha256(original_pdf).hexdigest()
        preflight, grobid_version = await asyncio.gather(
            self._preflight.inspect(original_pdf),
            self._grobid.version(),
        )
        if preflight.encrypted:
            raise InvalidDocumentError(
                "Password-protected PDFs cannot be parsed. Upload an unlocked copy."
            )

        working_pdf = original_pdf
        ocr_applied = False
        recovery_steps: list[str] = []
        if preflight.ocr_recommended and self._ocr_enabled:
            working_pdf = await self._preflight.apply_ocr(original_pdf)
            ocr_applied = True
            recovery_steps.append("ocr-preflight")

        try:
            result = await self._grobid.process_fulltext(working_pdf, filename)
        except GrobidNoTextError:
            if ocr_applied or not self._ocr_enabled:
                raise
            working_pdf = await self._preflight.apply_ocr(original_pdf)
            ocr_applied = True
            recovery_steps.append("ocr-after-grobid-no-blocks")
            result = await self._grobid.process_fulltext(working_pdf, filename)

        paper = normalize_tei(result.xml)
        if not paper.sections and self._fallback_flavor:
            try:
                fallback = await self._grobid.process_fulltext(
                    working_pdf,
                    filename,
                    flavor=self._fallback_flavor,
                )
                fallback_paper = normalize_tei(fallback.xml)
                if paper_body_characters(fallback_paper) > paper_body_characters(paper):
                    result = fallback
                    paper = fallback_paper
                    recovery_steps.append(f"grobid-flavor:{self._fallback_flavor}")
            except (GrobidRequestError, GrobidUnavailableError):
                recovery_steps.append(f"grobid-flavor-failed:{self._fallback_flavor}")

        citation_count = count_citations(paper)
        if citation_count and not paper.references:
            try:
                reference_result = await self._grobid.process_references(working_pdf, filename)
                merged_tei = merge_reference_tei(result.xml, reference_result.xml)
                merged_paper = normalize_tei(merged_tei)
                if len(merged_paper.references) > len(paper.references):
                    result = GrobidResult(
                        xml=merged_tei,
                        endpoint=result.endpoint,
                        options={
                            **result.options,
                            "fallbackRequests": [
                                {
                                    "endpoint": reference_result.endpoint,
                                    "options": reference_result.options,
                                }
                            ],
                        },
                    )
                    paper = merged_paper
                    recovery_steps.append("grobid-reference-only-fallback")
            except (GrobidRequestError, GrobidUnavailableError):
                recovery_steps.append("grobid-reference-only-fallback-failed")

        quality = assess_extraction_quality(paper, preflight)
        paper.warnings.extend(
            warning for warning in quality.warnings if warning not in paper.warnings
        )
        tei_sha256 = hashlib.sha256(result.xml).hexdigest()
        artifact_id = self._artifacts.save_tei(pdf_sha256, result.xml)
        paper.extraction = ExtractionMetadata(
            grobid_version=grobid_version,
            processed_at=datetime.now(UTC).isoformat(),
            duration_ms=round((time.perf_counter() - started) * 1000),
            pdf_sha256=pdf_sha256,
            tei_sha256=tei_sha256,
            tei_artifact_id=artifact_id,
            request_options=result.options,
            preflight=preflight,
            quality=quality,
            ocr_applied=ocr_applied,
            recovery_steps=recovery_steps,
        )
        return paper


def validate_pdf(content: bytes) -> bytes:
    if len(content) > MAX_PDF_SIZE:
        raise FileTooLargeError("PDF files must be 50 MB or smaller.")
    if not content.startswith(b"%PDF-"):
        raise UnsupportedMediaTypeError("The uploaded file is not a valid PDF.")
    return content


def normalize_tei(xml: bytes) -> Paper:
    if len(xml) > MAX_TEI_SIZE:
        raise FileTooLargeError("TEI XML files must be 100 MB or smaller.")
    if not xml.strip():
        raise InvalidDocumentError("The TEI XML file is empty.")
    try:
        return parse_tei(xml)
    except TEIParseError as exc:
        raise InvalidDocumentError(str(exc)) from exc


def paper_body_characters(paper: Paper) -> int:
    return sum(
        len(node.text if isinstance(node, TextNode) else node.raw_text)
        for section in paper.sections
        for paragraph in section.paragraphs
        for node in paragraph.nodes
    )


def count_citations(paper: Paper) -> int:
    return sum(
        isinstance(node, CitationNode)
        for section in paper.sections
        for paragraph in section.paragraphs
        for node in paragraph.nodes
    )


def assess_extraction_quality(
    paper: Paper,
    preflight: PdfPreflightReport,
) -> ExtractionQualityReport:
    body_characters = paper_body_characters(paper)
    citation_nodes = [
        node
        for section in paper.sections
        for paragraph in section.paragraphs
        for node in paragraph.nodes
        if isinstance(node, CitationNode)
    ]
    sentence_count = sum(
        len(paragraph.sentences)
        for section in paper.sections
        for paragraph in section.paragraphs
    )
    target_count = sum(len(node.items) for node in citation_nodes)
    unresolved_target_count = sum(
        len(node.resolution.unresolved_source_ids) for node in citation_nodes
    )
    resolved_target_ratio = (
        max(0, target_count - unresolved_target_count) / target_count
        if target_count
        else 1.0
    )
    parsed_reference_count = sum(
        reference.status == "parsed" for reference in paper.references
    )
    warnings: list[str] = []
    unusable = False

    if not paper.title:
        warnings.append("GROBID did not extract a paper title.")
    if not paper.sections or body_characters < 50:
        warnings.append("GROBID extracted too little body text for reliable review.")
        unusable = True
    if citation_nodes and not paper.references:
        warnings.append("In-text citations were found, but the bibliography is empty.")
    if paper.references and parsed_reference_count / len(paper.references) < 0.5:
        warnings.append("Fewer than half of the bibliography entries have complete core CSL fields.")
    if citation_nodes and resolved_target_ratio < 0.8:
        warnings.append("More than 20% of citation targets could not be linked to the bibliography.")
    if paper.sections and not sentence_count:
        warnings.append("GROBID did not return sentence segmentation for the extracted body.")
    if preflight.ocr_recommended:
        warnings.append("The original PDF contained little selectable text in sampled pages.")

    status = "unusable" if unusable else "warning" if warnings else "usable"
    return ExtractionQualityReport(
        status=status,
        body_characters=body_characters,
        section_count=len(paper.sections),
        sentence_count=sentence_count,
        citation_count=len(citation_nodes),
        reference_count=len(paper.references),
        parsed_reference_count=parsed_reference_count,
        resolved_target_ratio=round(resolved_target_ratio, 4),
        warnings=warnings,
    )


def merge_reference_tei(fulltext_xml: bytes, references_xml: bytes) -> bytes:
    """Replace an empty full-text bibliography with reference-only GROBID output."""
    try:
        full_root = ET.fromstring(fulltext_xml)
        reference_root = ET.fromstring(references_xml)
    except ET.ParseError as exc:
        raise InvalidDocumentError(f"GROBID fallback returned malformed TEI XML: {exc}.") from exc

    fallback_list = (
        reference_root
        if reference_root.tag == qname("listBibl")
        else reference_root.find(".//tei:listBibl", NS)
    )
    if fallback_list is None:
        return fulltext_xml

    target_list = full_root.find(".//tei:listBibl", NS)
    if target_list is None:
        text = full_root.find(".//tei:text", NS)
        if text is None:
            text = ET.SubElement(full_root, qname("text"))
        back = text.find("tei:back", NS)
        if back is None:
            back = ET.SubElement(text, qname("back"))
        bibliography_div = ET.SubElement(back, qname("div"), {"type": "references"})
        target_list = ET.SubElement(bibliography_div, qname("listBibl"))

    target_list.clear()
    for child in fallback_list:
        target_list.append(ET.fromstring(ET.tostring(child, encoding="utf-8")))
    ET.register_namespace("", TEI_NAMESPACE)
    return ET.tostring(full_root, encoding="utf-8", xml_declaration=True)
