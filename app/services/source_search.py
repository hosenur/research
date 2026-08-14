from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from app.config import (
    SOURCE_SEARCH_MAX_CANDIDATES,
    SOURCE_SEARCH_RESULTS_PER_PROVIDER,
)
from app.database.models import CitationAuditFindingRecord, ScholarlyWorkRecord
from app.repositories.openalex import OpenAlexError, OpenAlexRepository
from app.repositories.scholarly_works import (
    ScholarlyWorkRepository,
    lexical_score,
    normalize_title,
    works_from_response,
)
from app.repositories.semantic_scholar import SemanticScholarError, SemanticScholarRepository
from app.schemas.paper import Paper
from app.services.missing_works import known_work_keys


@dataclass(frozen=True)
class SourceSearchResult:
    work_id: str
    score: float
    reason: str


class CitationSourceSearcher:
    """Search locally first, then consult both provider caches/APIs for coverage."""

    def __init__(
        self,
        works: ScholarlyWorkRepository,
        openalex: OpenAlexRepository,
        semantic_scholar: SemanticScholarRepository,
    ) -> None:
        self._works = works
        self._openalex = openalex
        self._semantic_scholar = semantic_scholar

    async def search(
        self,
        paper: Paper,
        finding: CitationAuditFindingRecord,
    ) -> list[SourceSearchResult]:
        query = source_query(paper, finding)
        stored = await self._works.search(query, limit=SOURCE_SEARCH_MAX_CANDIDATES)
        excluded = nearby_cited_references(paper, finding)
        stored_candidates = self._rank_uncited(paper, query, stored, excluded, minimum_score=0.25)
        bibliography_candidates: list[SourceSearchResult] = []
        excluded_ids = {reference.id for reference in excluded}
        for reference in paper.references:
            if reference.id in excluded_ids or reference.openalex is None:
                continue
            work_id = await self._works.find_by_provider_id("openalex", reference.openalex.id)
            if work_id:
                bibliography_candidates.append(SourceSearchResult(work_id=work_id, score=0.92, reason="Exact unmatched bibliography work associated with this claim."))

        provider_errors: list[str] = []
        provider_payloads: dict[str, dict[str, Any] | None] = {}

        async def search_openalex() -> None:
            try:
                payload, _method = await self._openalex.search_related(
                    query,
                    per_page=SOURCE_SEARCH_RESULTS_PER_PROVIDER,
                )
                provider_payloads["openalex"] = payload
            except OpenAlexError as exc:
                provider_errors.append(exc.detail)

        async def search_semantic_scholar() -> None:
            try:
                provider_payloads["semantic-scholar"] = await self._semantic_scholar.search(
                    query,
                    limit=SOURCE_SEARCH_RESULTS_PER_PROVIDER,
                )
            except SemanticScholarError as exc:
                provider_errors.append(exc.detail)

        await asyncio.gather(search_openalex(), search_semantic_scholar())
        provider_rank: dict[str, float] = {}
        fetched_records: dict[str, ScholarlyWorkRecord] = {}
        for provider, payload in provider_payloads.items():
            parsed = works_from_response(provider, payload)
            ids = [work.provider_id for work in parsed]
            records = await self._works.by_provider_ids(provider, ids)
            by_provider_id = {
                record.provider_ids.get(provider): record
                for record in records
            }
            for index, work in enumerate(parsed):
                record = by_provider_id.get(work.provider_id)
                if record is None:
                    continue
                fetched_records[record.id] = record
                provider_rank[record.id] = max(
                    provider_rank.get(record.id, 0),
                    0.35 - index * 0.05,
                )

        fetched_candidates = self._rank_uncited(
            paper,
            query,
            list(fetched_records.values()),
            excluded,
            provider_rank=provider_rank,
        )
        by_work = {candidate.work_id: candidate for candidate in [*bibliography_candidates, *stored_candidates]}
        for candidate in fetched_candidates:
            current = by_work.get(candidate.work_id)
            if current is None or candidate.score > current.score:
                by_work[candidate.work_id] = candidate
        candidates = sorted(by_work.values(), key=lambda item: item.score, reverse=True)
        if not candidates and len(provider_errors) == 2:
            raise RuntimeError(" ".join(dict.fromkeys(provider_errors)))
        return candidates[:SOURCE_SEARCH_MAX_CANDIDATES]

    @staticmethod
    def _rank_uncited(
        paper: Paper,
        query: str,
        works: list[ScholarlyWorkRecord],
        excluded_references: list,
        *,
        provider_rank: dict[str, float] | None = None,
        minimum_score: float = 0,
    ) -> list[SourceSearchResult]:
        dois, arxivs, openalex_ids, titles = known_work_keys(excluded_references)
        paper_title = normalize_title(paper.title)
        ranked: list[SourceSearchResult] = []
        for work in works:
            if work.doi and work.doi.lower() in dois:
                continue
            if work.arxiv_id and work.arxiv_id.lower() in arxivs:
                continue
            if work.provider_ids.get("openalex") in openalex_ids:
                continue
            normalized = normalize_title(work.title)
            if normalized == paper_title or normalized in titles:
                continue
            score = min(1.0, lexical_score(query, work) + (provider_rank or {}).get(work.id, 0))
            if score < minimum_score:
                continue
            providers = ", ".join(sorted(work.provider_ids))
            ranked_by_provider = bool(provider_rank and work.id in provider_rank)
            ranked.append(
                SourceSearchResult(
                    work_id=work.id,
                    score=score,
                    reason=(
                        f"Ranked search result backed by {providers}."
                        if ranked_by_provider and providers
                        else (
                            f"Database-first topical match backed by {providers}."
                            if providers
                            else "Database-first topical match."
                        )
                    ),
                )
            )
        ranked.sort(key=lambda item: item.score, reverse=True)
        return ranked


def source_query(paper: Paper, finding: CitationAuditFindingRecord) -> str:
    # Put the claim first: local search keeps a bounded token window, and the
    # claim's distinctive terms are more useful than a generic paper title.
    parts = [finding.claim_text, finding.section_title, paper.title]
    return ". ".join(part.strip() for part in parts if part and part.strip())[:1_200]


def nearby_cited_references(paper: Paper, finding: CitationAuditFindingRecord) -> list:
    """Exclude only references cited in the finding's paragraph, not the whole paper."""
    for section in paper.sections:
        for paragraph in section.paragraphs:
            if paragraph.id != finding.paragraph_id:
                continue
            ids = {
                source_id
                for node in paragraph.nodes
                if hasattr(node, "source_ids")
                for source_id in node.source_ids
            }
            return [reference for reference in paper.references if reference.id in ids]
    return []
