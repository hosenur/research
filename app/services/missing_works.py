from __future__ import annotations

import re
from typing import Iterable

from app.config import MISSING_WORK_MAX_CLAIMS, MISSING_WORK_RESULTS_PER_CLAIM
from app.repositories.openalex import OpenAlexError, OpenAlexRepository
from app.schemas.paper import (
    CitationNode,
    ClaimQuery,
    MissingWorkFinding,
    MissingWorkReport,
    Paper,
    Paragraph,
    Reference,
    Section,
    TextNode,
)
from app.services.openalex import (
    first_results,
    normalize_arxiv,
    normalize_doi,
    normalize_title,
    title_similarity,
    work_from_payload,
)

PREFERRED_SECTIONS = (
    "introduction",
    "related work",
    "background",
    "related works",
    "prior work",
    "literature",
)
SKIP_SECTIONS = (
    "acknowledg",
    "appendix",
    "references",
    "bibliography",
    "conclusion",
)
CLAIM_CUES = re.compile(
    r"\b(we propose|we present|we show|we introduce|however|although|"
    r"prior work|previous work|existing|state of the art|unlike|in contrast)\b",
    re.I,
)


def paragraph_text(paragraph: Paragraph) -> str:
    parts: list[str] = []
    for node in paragraph.nodes:
        if isinstance(node, TextNode):
            parts.append(node.text)
        elif isinstance(node, CitationNode):
            parts.append(node.raw_text)
    return re.sub(r"\s+", " ", "".join(parts)).strip()


def split_sentences(text: str) -> list[str]:
    pieces = re.split(r"(?<=[.!?])\s+", text)
    return [piece.strip() for piece in pieces if len(piece.strip()) > 40]


def section_priority(section: Section) -> int:
    title = section.title.lower()
    if any(skip in title for skip in SKIP_SECTIONS):
        return 99
    for index, name in enumerate(PREFERRED_SECTIONS):
        if name in title:
            return index
    return 20


def extract_claims(paper: Paper, limit: int = MISSING_WORK_MAX_CLAIMS) -> list[ClaimQuery]:
    claims: list[ClaimQuery] = []
    seen: set[str] = set()
    for section in sorted(paper.sections, key=section_priority):
        if section_priority(section) == 99:
            continue
        sentences: list[str] = []
        for paragraph in section.paragraphs:
            sentences.extend(split_sentences(paragraph_text(paragraph)))
        ranked = sorted(
            sentences,
            key=lambda sentence: (0 if CLAIM_CUES.search(sentence) else 1, -len(sentence)),
        )
        for sentence in ranked[:2]:
            key = normalize_title(sentence)
            if key in seen:
                continue
            seen.add(key)
            claims.append(
                ClaimQuery(
                    section_id=section.id,
                    section_title=section.title,
                    text=sentence,
                )
            )
            if len(claims) >= limit:
                return claims
    if not claims and paper.abstract:
        claims.append(
            ClaimQuery(
                section_id="abstract",
                section_title="Abstract",
                text=split_sentences(paper.abstract)[0] if split_sentences(paper.abstract) else paper.abstract,
            )
        )
    return claims


def known_work_keys(references: Iterable[Reference]) -> tuple[set[str], set[str], set[str], set[str]]:
    dois: set[str] = set()
    arxivs: set[str] = set()
    ids: set[str] = set()
    titles: set[str] = set()
    for reference in references:
        doi, arxiv, title, _, _ = _lookup_bits(reference)
        if doi:
            dois.add(doi.lower())
        if arxiv:
            arxivs.add(arxiv.lower())
        if title:
            titles.add(normalize_title(title))
        if reference.openalex:
            ids.add(reference.openalex.id)
            if reference.openalex.doi:
                dois.add(reference.openalex.doi.lower())
            if reference.openalex.title:
                titles.add(normalize_title(reference.openalex.title))
    return dois, arxivs, ids, titles


def cited_references(paper: Paper) -> list[Reference]:
    """Return bibliography entries that have an actual in-text citation anchor.

    A bibliography can legitimately contain a paper whose inline citation was
    accidentally omitted. Treating every bibliography row as already cited
    prevents the audit from recovering exactly that missing source.
    """
    cited_ids: set[str] = set()
    for section in paper.sections:
        for paragraph in section.paragraphs:
            for node in paragraph.nodes:
                if isinstance(node, CitationNode):
                    cited_ids.update(node.source_ids)
    return [reference for reference in paper.references if reference.id in cited_ids]


def _lookup_bits(reference: Reference) -> tuple[str | None, str | None, str | None, int | None, str | None]:
    from app.services.openalex import reference_lookup_fields

    return reference_lookup_fields(reference)


def already_cited(
    work: dict,
    dois: set[str],
    arxivs: set[str],
    ids: set[str],
    titles: set[str],
) -> bool:
    openalex_id = str(work.get("id") or "")
    if openalex_id and openalex_id in ids:
        return True
    doi = normalize_doi(work.get("doi"))
    if doi and doi.lower() in dois:
        return True
    ids_blob = work.get("ids") or {}
    arxiv = normalize_arxiv((ids_blob.get("arxiv") if isinstance(ids_blob, dict) else None))
    if arxiv and arxiv.lower() in arxivs:
        return True
    title = normalize_title(work.get("display_name") or work.get("title"))
    if title and title in titles:
        return True
    return any(title and title_similarity(title, known) >= 0.92 for known in titles)


class MissingWorkFinder:
    def __init__(self, repository: OpenAlexRepository) -> None:
        self._repository = repository

    async def find(self, paper: Paper) -> MissingWorkReport:
        queries = extract_claims(paper)
        dois, arxivs, ids, titles = known_work_keys(cited_references(paper))
        findings: list[MissingWorkFinding] = []
        seen_works: set[str] = set()
        warnings: list[str] = []

        if not queries:
            warnings.append("No claim-like sentences were found to search.")
            return MissingWorkReport(queries=[], findings=[], warnings=warnings)

        for query in queries:
            try:
                payload, method = await self._repository.search_related(
                    f"{paper.title}. {query.text}",
                    per_page=MISSING_WORK_RESULTS_PER_CLAIM,
                )
            except OpenAlexError as exc:
                query.status = "error"
                query.error = exc.detail
                continue

            candidates = first_results(payload)
            if not candidates:
                query.status = "empty"
                query.error = "OpenAlex returned no related works."
                continue

            added = 0
            for candidate in candidates:
                work_id = str(candidate.get("id") or "")
                if not work_id or work_id in seen_works:
                    continue
                if already_cited(candidate, dois, arxivs, ids, titles):
                    continue
                seen_works.add(work_id)
                work = work_from_payload(candidate, "search", "medium")
                findings.append(
                    MissingWorkFinding(
                        section_id=query.section_id,
                        section_title=query.section_title,
                        claim=query.text,
                        work=work,
                        reason=f"OpenAlex {method} search for this claim.",
                    )
                )
                added += 1
                if added >= 3:
                    break

        if any(query.status == "error" for query in queries):
            warnings.append("Some claim searches failed.")
        if any(query.status == "empty" for query in queries) and not findings:
            warnings.append("OpenAlex found no related work for the extracted claims.")
        warnings.append(f"Found {len(findings)} candidate papers not already in the bibliography.")
        return MissingWorkReport(queries=queries, findings=findings, warnings=warnings)
