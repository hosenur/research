from __future__ import annotations

import asyncio
import re
from typing import Any, Literal

from app.config import OPENALEX_CONCURRENCY
from app.repositories.openalex import OpenAlexError, OpenAlexRepository
from app.schemas.paper import OpenAlexWork, Paper, Reference

MatchMethod = Literal["doi", "arxiv", "title", "search"]
Confidence = Literal["high", "medium"]

_TITLE_STOPWORDS = {
    "a",
    "an",
    "and",
    "for",
    "from",
    "in",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}


def reconstruct_abstract(inverted_index: dict[str, list[int]] | None) -> str | None:
    if not inverted_index:
        return None
    positions: list[tuple[int, str]] = []
    for word, indexes in inverted_index.items():
        for index in indexes:
            positions.append((index, word))
    if not positions:
        return None
    positions.sort()
    return " ".join(word for _, word in positions)


def normalize_doi(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", value.strip(), flags=re.I)
    cleaned = cleaned.rstrip(".")
    return cleaned or None


def normalize_arxiv(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = re.sub(r"^arxiv:\s*", "", value.strip(), flags=re.I)
    cleaned = re.sub(r"v\d+(?:\[[^]]+\])?$", "", cleaned)
    return cleaned or None


def normalize_title(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def title_tokens(value: str | None) -> set[str]:
    return {
        token
        for token in normalize_title(value).split()
        if token and token not in _TITLE_STOPWORDS
    }


def title_similarity(left: str | None, right: str | None) -> float:
    left_tokens = title_tokens(left)
    right_tokens = title_tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    overlap = len(left_tokens & right_tokens)
    return overlap / max(len(left_tokens), len(right_tokens))


def first_results(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not payload:
        return []
    if "results" in payload:
        return [item for item in payload.get("results") or [] if isinstance(item, dict)]
    return [payload]


def work_from_payload(
    payload: dict[str, Any],
    match_method: MatchMethod,
    confidence: Confidence,
) -> OpenAlexWork:
    location = payload.get("primary_location") or {}
    landing = location.get("landing_page_url") if isinstance(location, dict) else None
    ids = payload.get("ids") or {}
    openalex_id = payload.get("id") or ids.get("openalex")
    return OpenAlexWork(
        id=str(openalex_id),
        doi=normalize_doi(payload.get("doi") or ids.get("doi")),
        title=payload.get("display_name") or payload.get("title"),
        year=payload.get("publication_year"),
        abstract=reconstruct_abstract(payload.get("abstract_inverted_index")),
        cited_by_count=payload.get("cited_by_count"),
        landing_page_url=landing or str(openalex_id) if openalex_id else None,
        match_method=match_method,
        confidence=confidence,
    )


def first_author_family(reference: Reference) -> str | None:
    authors = reference.csl.author if reference.csl else []
    if not authors:
        raw_authors = reference.raw_fields.get("authors")
        if isinstance(raw_authors, list) and raw_authors:
            first = raw_authors[0]
            if isinstance(first, dict):
                family = first.get("family") or first.get("literal")
                return family if isinstance(family, str) and family.strip() else None
        return None
    family = authors[0].family or authors[0].literal
    return family.strip() if family else None


def candidate_author_names(payload: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for authorship in payload.get("authorships") or []:
        if not isinstance(authorship, dict):
            continue
        author = authorship.get("author") or {}
        display = author.get("display_name") if isinstance(author, dict) else None
        raw = authorship.get("raw_author_name")
        for value in (display, raw):
            if isinstance(value, str) and value.strip():
                names.append(value)
    return names


def author_overlap(family: str | None, payload: dict[str, Any]) -> bool:
    if not family:
        return False
    needle = normalize_title(family)
    if not needle:
        return False
    return any(needle in normalize_title(name) for name in candidate_author_names(payload))


def reference_lookup_fields(
    reference: Reference,
) -> tuple[str | None, str | None, str | None, int | None, str | None]:
    identifiers = {}
    if isinstance(reference.raw_fields.get("identifiers"), dict):
        identifiers = reference.raw_fields["identifiers"]
    doi = normalize_doi((reference.csl.doi if reference.csl else None) or identifiers.get("doi"))
    arxiv = normalize_arxiv(
        (reference.csl.archive_location if reference.csl else None) or identifiers.get("arxiv")
    )
    title = (reference.csl.title if reference.csl else None) or reference.raw_fields.get("title")
    year = None
    if reference.csl and reference.csl.issued and reference.csl.issued.date_parts:
        year = reference.csl.issued.date_parts[0][0]
    return doi, arxiv, title if isinstance(title, str) else None, year, first_author_family(reference)


def choose_title_match(
    candidates: list[dict[str, Any]],
    title: str,
    year: int | None,
    author: str | None = None,
) -> tuple[dict[str, Any], Confidence] | None:
    scored: list[tuple[float, dict[str, Any]]] = []
    for candidate in candidates:
        candidate_title = candidate.get("display_name") or candidate.get("title")
        score = title_similarity(title, candidate_title)
        if author_overlap(author, candidate):
            score += 0.2
        if year is not None and candidate.get("publication_year") == year:
            score += 0.05
        if score >= 0.8:
            scored.append((score, candidate))
    if not scored:
        return None
    scored.sort(key=lambda item: item[0], reverse=True)
    best_score, best = scored[0]
    if len(scored) > 1 and best_score - scored[1][0] < 0.08:
        return None
    confidence: Confidence = "high" if best_score >= 0.95 or author_overlap(author, best) else "medium"
    return best, confidence


class OpenAlexEnricher:
    """Attach OpenAlex records to parsed bibliography entries."""

    def __init__(self, repository: OpenAlexRepository) -> None:
        self._repository = repository

    async def enrich_paper(self, paper: Paper) -> Paper:
        semaphore = asyncio.Semaphore(OPENALEX_CONCURRENCY)
        await asyncio.gather(*(self.enrich_reference(reference, semaphore) for reference in paper.references))

        matched = sum(1 for reference in paper.references if reference.openalex_status == "matched")
        unmatched = sum(1 for reference in paper.references if reference.openalex_status == "unmatched")
        errors = sum(1 for reference in paper.references if reference.openalex_status == "error")
        paper.warnings = [
            warning for warning in paper.warnings if not warning.startswith("OpenAlex matched ")
        ]
        if paper.references:
            paper.warnings.append(
                f"OpenAlex matched {matched}/{len(paper.references)} references"
                + (f"; {unmatched} unmatched" if unmatched else "")
                + (f"; {errors} lookup errors" if errors else "")
                + "."
            )
        return paper

    async def enrich_reference(
        self,
        reference: Reference,
        semaphore: asyncio.Semaphore | None = None,
    ) -> None:
        doi, arxiv, title, year, author = reference_lookup_fields(reference)
        if not doi and not arxiv and not title:
            reference.openalex_status = "skipped"
            reference.openalex_error = "No DOI, arXiv id, or title available to look up."
            return

        limiter = semaphore or asyncio.Semaphore(1)
        async with limiter:
            try:
                work, method, confidence = await self._lookup(doi, arxiv, title, year, author)
            except OpenAlexError as exc:
                reference.openalex_status = "error"
                reference.openalex_error = exc.detail
                return

        if work is None:
            reference.openalex_status = "unmatched"
            reference.openalex_error = "No OpenAlex work matched this reference."
            return

        reference.openalex = work_from_payload(work, method, confidence)
        reference.openalex_status = "matched"

    async def _lookup(
        self,
        doi: str | None,
        arxiv: str | None,
        title: str | None,
        year: int | None,
        author: str | None,
    ) -> tuple[dict[str, Any] | None, MatchMethod, Confidence]:
        if doi:
            payload = await self._repository.get_by_doi(doi)
            matches = first_results(payload)
            if matches:
                return matches[0], "doi", "high"

        if arxiv:
            payload = await self._repository.get_by_arxiv(arxiv)
            matches = first_results(payload)
            if matches:
                return matches[0], "arxiv", "high"

        if title:
            payload = await self._repository.search_by_title(title, year, author)
            chosen = choose_title_match(first_results(payload), title, year, author)
            if chosen:
                return chosen[0], "title", chosen[1]

        return None, "title", "medium"
