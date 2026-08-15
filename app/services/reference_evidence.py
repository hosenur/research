from __future__ import annotations

import asyncio
from dataclasses import dataclass

from app.repositories.scholarly_works import (
    ScholarlyWorkData,
    ScholarlyWorkRepository,
    works_from_response,
)
from app.repositories.semantic_scholar import (
    SemanticScholarError,
    SemanticScholarRepository,
)
from app.schemas.paper import Reference
from app.services.openalex import (
    OpenAlexEnricher,
    first_author_family,
    normalize_arxiv,
    normalize_doi,
    reference_lookup_fields,
    title_similarity,
)


@dataclass(frozen=True)
class ProviderReferenceEvidence:
    provider: str
    status: str
    work_id: str | None = None
    work_json: dict | None = None
    match_method: str | None = None
    confidence: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class ResolvedReferenceEvidence:
    reference: Reference
    providers: tuple[ProviderReferenceEvidence, ...]


class BibliographyEvidenceResolver:
    """Resolve one parsed reference through both scholarly-provider adapters."""

    def __init__(
        self,
        openalex: OpenAlexEnricher,
        semantic_scholar: SemanticScholarRepository,
        works: ScholarlyWorkRepository,
    ) -> None:
        self._openalex = openalex
        self._semantic_scholar = semantic_scholar
        self._works = works

    async def resolve(
        self,
        reference: Reference,
        semaphore: asyncio.Semaphore,
    ) -> ResolvedReferenceEvidence:
        _, semantic = await asyncio.gather(
            self._resolve_openalex(reference, semaphore),
            self._resolve_semantic_scholar(reference, semaphore),
        )
        openalex_work_id = None
        if reference.openalex is not None:
            openalex_work_id = await self._works.find_by_provider_id(
                "openalex", reference.openalex.id
            )
        openalex = ProviderReferenceEvidence(
            provider="openalex",
            status=reference.openalex_status or "error",
            work_id=openalex_work_id,
            work_json=(
                reference.openalex.model_dump(mode="json", by_alias=True)
                if reference.openalex
                else None
            ),
            match_method=(reference.openalex.match_method if reference.openalex else None),
            confidence=(reference.openalex.confidence if reference.openalex else None),
            error=reference.openalex_error,
        )
        return ResolvedReferenceEvidence(reference, (openalex, semantic))

    async def _resolve_openalex(
        self,
        reference: Reference,
        semaphore: asyncio.Semaphore,
    ) -> None:
        await self._openalex.enrich_reference(reference, semaphore)

    async def _resolve_semantic_scholar(
        self,
        reference: Reference,
        semaphore: asyncio.Semaphore,
    ) -> ProviderReferenceEvidence:
        doi, arxiv, title, year, author = reference_lookup_fields(reference)
        query = doi or arxiv or " ".join(
            value for value in (title, author, str(year) if year else None) if value
        )
        if not query:
            return ProviderReferenceEvidence(
                provider="semantic-scholar",
                status="skipped",
                error="No DOI, arXiv id, or title is available for Semantic Scholar lookup.",
            )
        try:
            async with semaphore:
                payload = await self._semantic_scholar.search(query, limit=5)
        except SemanticScholarError as exc:
            return ProviderReferenceEvidence(
                provider="semantic-scholar",
                status="error",
                error=exc.detail,
            )

        match = choose_semantic_scholar_match(
            works_from_response("semantic-scholar", payload),
            doi=doi,
            arxiv=arxiv,
            title=title,
            year=year,
            author=author,
        )
        if match is None:
            return ProviderReferenceEvidence(
                provider="semantic-scholar",
                status="unmatched",
                error="No unambiguous Semantic Scholar work matched this reference.",
            )
        work, method, confidence = match
        work_id = await self._works.find_by_provider_id(
            "semantic-scholar", work.provider_id
        )
        if work_id is None:
            return ProviderReferenceEvidence(
                provider="semantic-scholar",
                status="error",
                error="The matched Semantic Scholar work was not normalized into the cache.",
            )
        return ProviderReferenceEvidence(
            provider="semantic-scholar",
            status="matched",
            work_id=work_id,
            work_json=work.raw,
            match_method=method,
            confidence=confidence,
        )


def choose_semantic_scholar_match(
    candidates: list[ScholarlyWorkData],
    *,
    doi: str | None,
    arxiv: str | None,
    title: str | None,
    year: int | None,
    author: str | None,
) -> tuple[ScholarlyWorkData, str, str] | None:
    normalized_doi = normalize_doi(doi)
    normalized_arxiv = normalize_arxiv(arxiv)
    if normalized_doi:
        exact = [work for work in candidates if normalize_doi(work.doi) == normalized_doi]
        if len(exact) == 1:
            return exact[0], "doi", "high"
    if normalized_arxiv:
        exact = [
            work
            for work in candidates
            if normalize_arxiv(work.arxiv_id) == normalized_arxiv
        ]
        if len(exact) == 1:
            return exact[0], "arxiv", "high"
    if not title:
        return None

    scored: list[tuple[float, ScholarlyWorkData]] = []
    for work in candidates:
        similarity = title_similarity(title, work.title)
        author_match = semantic_author_overlap(author, work)
        score = similarity
        if author_match:
            score += 0.2
        if year is not None and work.year == year:
            score += 0.05
        if similarity >= 0.8 and score >= 0.9:
            scored.append((score, work))
    scored.sort(key=lambda item: item[0], reverse=True)
    if not scored or (len(scored) > 1 and scored[0][0] - scored[1][0] < 0.08):
        return None
    score, work = scored[0]
    confidence = "high" if score >= 1 or semantic_author_overlap(author, work) else "medium"
    return work, "title", confidence


def semantic_author_overlap(author: str | None, work: ScholarlyWorkData) -> bool:
    if not author:
        return False
    needle = author.casefold().strip()
    return any(
        needle in str(candidate.get("name") or "").casefold()
        for candidate in work.authors
    )
