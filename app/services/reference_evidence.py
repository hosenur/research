from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from typing import Literal

from app.repositories.scholarly_works import (
    ScholarlyWorkData,
    ScholarlyWorkRepository,
    normalize_title,
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
    provider_id: str | None = None
    title: str | None = None
    abstract: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    year: int | None = None
    authors: tuple[str, ...] = ()
    source_url: str | None = None


@dataclass(frozen=True)
class ReferenceEvidenceReconciliation:
    status: Literal["agreed", "single-provider", "ambiguous", "unavailable"]
    providers: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class ResolvedReferenceEvidence:
    reference: Reference
    providers: tuple[ProviderReferenceEvidence, ...]
    reconciliation: ReferenceEvidenceReconciliation


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
        openalex_data = None
        if reference.openalex is not None:
            openalex_work_id = await self._works.find_by_provider_id(
                "openalex", reference.openalex.id
            )
            openalex_data = await self._provider_work(
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
            **provider_projection(openalex_data),
        )
        providers = (openalex, semantic)
        reconciliation = reconcile_provider_matches(providers)
        if reconciliation.status == "ambiguous":
            providers = tuple(
                replace(
                    evidence,
                    status="ambiguous",
                    error=reconciliation.reason,
                )
                if evidence.status == "matched"
                else evidence
                for evidence in providers
            )
        return ResolvedReferenceEvidence(reference, providers, reconciliation)

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
            **provider_projection(work),
        )

    async def _provider_work(
        self, provider: str, provider_id: str
    ) -> ScholarlyWorkData | None:
        records = await self._works.by_provider_ids(provider, [provider_id])
        if not records:
            return None
        payload = records[0].provider_payloads.get(provider)
        return next(
            (
                work
                for work in works_from_response(provider, payload)
                if work.provider_id == provider_id
            ),
            None,
        )


def provider_projection(work: ScholarlyWorkData | None) -> dict:
    if work is None:
        return {}
    return {
        "provider_id": work.provider_id,
        "title": work.title,
        "abstract": work.abstract,
        "doi": work.doi,
        "arxiv_id": work.arxiv_id,
        "year": work.year,
        "authors": tuple(
            str(author.get("name") or "").strip()
            for author in work.authors
            if str(author.get("name") or "").strip()
        ),
        "source_url": work.landing_page_url,
    }


def reconcile_provider_matches(
    providers: tuple[ProviderReferenceEvidence, ...],
) -> ReferenceEvidenceReconciliation:
    matched = tuple(item for item in providers if item.status == "matched")
    names = tuple(item.provider for item in matched)
    if not matched:
        return ReferenceEvidenceReconciliation(
            status="unavailable",
            providers=(),
            reason="No provider returned an unambiguous reference match.",
        )
    if len(matched) == 1:
        return ReferenceEvidenceReconciliation(
            status="single-provider",
            providers=names,
            reason=f"Only {matched[0].provider} supplied a usable match.",
        )
    if all(strong_identity_agreement(matched[0], item) for item in matched[1:]):
        return ReferenceEvidenceReconciliation(
            status="agreed",
            providers=names,
            reason="Provider matches agree on a strong scholarly-work identity.",
        )
    return ReferenceEvidenceReconciliation(
        status="ambiguous",
        providers=names,
        reason=(
            "Provider matches disagree on DOI, arXiv ID, or exact title/year/author identity; "
            "their metadata and abstracts were not combined."
        ),
    )


def strong_identity_agreement(
    left: ProviderReferenceEvidence,
    right: ProviderReferenceEvidence,
) -> bool:
    left_doi, right_doi = normalize_doi(left.doi), normalize_doi(right.doi)
    if left_doi and right_doi:
        return left_doi == right_doi
    left_arxiv, right_arxiv = normalize_arxiv(left.arxiv_id), normalize_arxiv(
        right.arxiv_id
    )
    if left_arxiv and right_arxiv:
        return left_arxiv == right_arxiv
    left_author = author_family(left.authors)
    right_author = author_family(right.authors)
    return bool(
        left.title
        and right.title
        and normalize_title(left.title) == normalize_title(right.title)
        and left.year is not None
        and left.year == right.year
        and left_author
        and left_author == right_author
    )


def author_family(authors: tuple[str, ...]) -> str | None:
    if not authors:
        return None
    parts = normalize_title(authors[0]).split()
    return parts[-1] if parts else None


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
