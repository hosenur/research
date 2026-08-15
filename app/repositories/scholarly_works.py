from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from typing import Any, Iterable

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.cache.jsonl import JsonlCache
from app.database.models import ProviderCacheRecord, ScholarlyWorkRecord


@dataclass(frozen=True)
class CacheLookup:
    found: bool
    value: Any | None = None


@dataclass(frozen=True)
class ScholarlyWorkData:
    provider: str
    provider_id: str
    title: str
    year: int | None
    abstract: str | None
    doi: str | None
    arxiv_id: str | None
    authors: list[dict[str, str]]
    landing_page_url: str | None
    cited_by_count: int | None
    raw: dict[str, Any]


class ScholarlyWorkRepository:
    """Durable provider response cache and canonical scholarly-work index."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get_cached(self, provider: str, cache_key: str) -> CacheLookup:
        async with self._session_factory() as session:
            record = await session.get(
                ProviderCacheRecord,
                {"provider": provider, "cache_key": cache_key},
            )
            if record is None:
                return CacheLookup(False)
            return CacheLookup(True, None if record.is_negative else record.response_json)

    async def store_response(
        self,
        provider: str,
        cache_key: str,
        response: Any | None,
        *,
        request: dict[str, Any] | None = None,
    ) -> int:
        works = works_from_response(provider, response)
        async with self._session_factory() as session:
            statement = insert(ProviderCacheRecord).values(
                provider=provider,
                cache_key=cache_key,
                request_json=request,
                response_json=response,
                is_negative=response is None,
            )
            statement = statement.on_conflict_do_update(
                index_elements=["provider", "cache_key"],
                set_={
                    "request_json": statement.excluded.request_json,
                    "response_json": statement.excluded.response_json,
                    "is_negative": statement.excluded.is_negative,
                },
            )
            await session.execute(statement)
            for work in works:
                await self._upsert_work(session, work)
            await session.commit()
        return len(works)

    async def backfill_openalex_jsonl(self, cache: JsonlCache) -> tuple[int, int]:
        entries = 0
        works = 0
        for key, value in cache.items():
            if not key.startswith("openalex:"):
                continue
            existing = await self.get_cached("openalex", key)
            if existing.found:
                continue
            works += await self.store_response(
                "openalex",
                key,
                value,
                request={"legacyJsonlKey": key},
            )
            entries += 1
        return entries, works

    async def search(self, query: str, *, limit: int = 20) -> list[ScholarlyWorkRecord]:
        tokens = query_tokens(query)
        if not tokens:
            return []
        conditions = [
            or_(
                ScholarlyWorkRecord.title_normalized.contains(token),
                ScholarlyWorkRecord.abstract.ilike(f"%{token}%"),
            )
            for token in tokens[:8]
        ]
        async with self._session_factory() as session:
            result = await session.scalars(
                select(ScholarlyWorkRecord)
                .where(or_(*conditions))
                .order_by(ScholarlyWorkRecord.cited_by_count.desc().nullslast())
                .limit(max(limit * 4, 40))
            )
            records = list(result)
        records.sort(key=lambda record: lexical_score(query, record), reverse=True)
        return records[:limit]

    async def by_provider_ids(
        self,
        provider: str,
        provider_ids: list[str],
    ) -> list[ScholarlyWorkRecord]:
        if not provider_ids:
            return []
        async with self._session_factory() as session:
            result = await session.scalars(
                select(ScholarlyWorkRecord).where(
                    ScholarlyWorkRecord.provider_ids[provider].astext.in_(provider_ids)
                )
            )
            return list(result)

    async def find_by_provider_id(self, provider: str, provider_id: str) -> str | None:
        async with self._session_factory() as session:
            return await session.scalar(
                select(ScholarlyWorkRecord.id).where(
                    ScholarlyWorkRecord.provider_ids[provider].astext == provider_id
                )
            )

    async def find_by_identity(
        self,
        *,
        doi: str | None = None,
        arxiv_id: str | None = None,
        title: str | None = None,
        year: int | None = None,
    ) -> ScholarlyWorkRecord | None:
        """Find cached evidence using only strong bibliography identities."""
        normalized_doi = normalize_doi(doi)
        normalized_arxiv = normalize_arxiv(arxiv_id)
        normalized_title = normalize_title(title or "")
        conditions = []
        if normalized_doi:
            conditions.append(ScholarlyWorkRecord.doi == normalized_doi)
        if normalized_arxiv:
            conditions.append(ScholarlyWorkRecord.arxiv_id == normalized_arxiv)
        if normalized_title and year is not None:
            conditions.append(
                and_(
                    ScholarlyWorkRecord.title_normalized == normalized_title,
                    ScholarlyWorkRecord.year == year,
                )
            )
        if not conditions:
            return None
        async with self._session_factory() as session:
            return await session.scalar(
                select(ScholarlyWorkRecord).where(or_(*conditions)).limit(1)
            )

    async def _upsert_work(
        self,
        session: AsyncSession,
        work: ScholarlyWorkData,
    ) -> str:
        title_normalized = normalize_title(work.title)
        canonical_key = canonical_work_key(work)
        identity_conditions = [
            ScholarlyWorkRecord.canonical_key == canonical_key,
            ScholarlyWorkRecord.provider_ids[work.provider].astext == work.provider_id,
        ]
        if work.doi:
            identity_conditions.append(ScholarlyWorkRecord.doi == work.doi)
        if work.arxiv_id:
            identity_conditions.append(ScholarlyWorkRecord.arxiv_id == work.arxiv_id)
        existing = await session.scalar(
            select(ScholarlyWorkRecord).where(or_(*identity_conditions)).limit(1)
        )
        if existing is not None:
            canonical_key = existing.canonical_key

        work_id = existing.id if existing else str(uuid.uuid4())
        values = {
            "id": work_id,
            "canonical_key": canonical_key,
            "title": work.title,
            "title_normalized": title_normalized,
            "year": work.year,
            "abstract": work.abstract,
            "doi": work.doi,
            "arxiv_id": work.arxiv_id,
            "authors": work.authors,
            "landing_page_url": work.landing_page_url,
            "cited_by_count": work.cited_by_count,
            "provider_ids": {work.provider: work.provider_id},
            "provider_payloads": {work.provider: work.raw},
        }
        statement = insert(ScholarlyWorkRecord).values(**values)
        excluded = statement.excluded
        statement = statement.on_conflict_do_update(
            index_elements=["canonical_key"],
            set_={
                "title": excluded.title,
                "title_normalized": excluded.title_normalized,
                "year": func.coalesce(excluded.year, ScholarlyWorkRecord.year),
                "abstract": func.coalesce(excluded.abstract, ScholarlyWorkRecord.abstract),
                "doi": func.coalesce(excluded.doi, ScholarlyWorkRecord.doi),
                "arxiv_id": func.coalesce(excluded.arxiv_id, ScholarlyWorkRecord.arxiv_id),
                "authors": case(
                    (func.jsonb_array_length(excluded.authors) > 0, excluded.authors),
                    else_=ScholarlyWorkRecord.authors,
                ),
                "landing_page_url": func.coalesce(
                    excluded.landing_page_url,
                    ScholarlyWorkRecord.landing_page_url,
                ),
                "cited_by_count": func.greatest(
                    excluded.cited_by_count,
                    ScholarlyWorkRecord.cited_by_count,
                ),
                "provider_ids": ScholarlyWorkRecord.provider_ids.op("||")(excluded.provider_ids),
                "provider_payloads": ScholarlyWorkRecord.provider_payloads.op("||")(
                    excluded.provider_payloads
                ),
            },
        )
        await session.execute(statement)
        return work_id


def works_from_response(provider: str, response: Any | None) -> list[ScholarlyWorkData]:
    if not isinstance(response, dict):
        return []
    raw_items: Iterable[Any]
    if isinstance(response.get("results"), list):
        raw_items = response["results"]
    elif isinstance(response.get("data"), list):
        raw_items = response["data"]
    else:
        raw_items = [response]
    parser = openalex_work if provider == "openalex" else semantic_scholar_work
    parsed: list[ScholarlyWorkData] = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        work = parser(raw)
        if work is not None:
            parsed.append(work)
    return parsed


def openalex_work(raw: dict[str, Any]) -> ScholarlyWorkData | None:
    ids = raw.get("ids") if isinstance(raw.get("ids"), dict) else {}
    provider_id = raw.get("id") or ids.get("openalex")
    title = raw.get("display_name") or raw.get("title")
    if not provider_id or not isinstance(title, str) or not title.strip():
        return None
    location = raw.get("primary_location") if isinstance(raw.get("primary_location"), dict) else {}
    return ScholarlyWorkData(
        provider="openalex",
        provider_id=str(provider_id),
        title=title.strip(),
        year=as_int(raw.get("publication_year")),
        abstract=reconstruct_abstract(raw.get("abstract_inverted_index")),
        doi=normalize_doi(raw.get("doi") or ids.get("doi")),
        arxiv_id=normalize_arxiv(ids.get("arxiv")),
        authors=openalex_authors(raw),
        landing_page_url=location.get("landing_page_url") or str(provider_id),
        cited_by_count=as_int(raw.get("cited_by_count")),
        raw=raw,
    )


def semantic_scholar_work(raw: dict[str, Any]) -> ScholarlyWorkData | None:
    provider_id = raw.get("paperId")
    title = raw.get("title")
    if not provider_id or not isinstance(title, str) or not title.strip():
        return None
    external_ids = raw.get("externalIds") if isinstance(raw.get("externalIds"), dict) else {}
    pdf = raw.get("openAccessPdf") if isinstance(raw.get("openAccessPdf"), dict) else {}
    authors = [
        {"name": author["name"]}
        for author in raw.get("authors") or []
        if isinstance(author, dict) and isinstance(author.get("name"), str)
    ]
    return ScholarlyWorkData(
        provider="semantic-scholar",
        provider_id=str(provider_id),
        title=title.strip(),
        year=as_int(raw.get("year")),
        abstract=raw.get("abstract") if isinstance(raw.get("abstract"), str) else None,
        doi=normalize_doi(external_ids.get("DOI")),
        arxiv_id=normalize_arxiv(external_ids.get("ArXiv")),
        authors=authors,
        landing_page_url=raw.get("url") or pdf.get("url"),
        cited_by_count=as_int(raw.get("citationCount")),
        raw=raw,
    )


def openalex_authors(raw: dict[str, Any]) -> list[dict[str, str]]:
    authors: list[dict[str, str]] = []
    for authorship in raw.get("authorships") or []:
        if not isinstance(authorship, dict):
            continue
        author = authorship.get("author") if isinstance(authorship.get("author"), dict) else {}
        name = author.get("display_name") or authorship.get("raw_author_name")
        if isinstance(name, str) and name.strip():
            authors.append({"name": name.strip()})
    return authors


def reconstruct_abstract(inverted: Any) -> str | None:
    if not isinstance(inverted, dict):
        return None
    positions: list[tuple[int, str]] = []
    for word, indexes in inverted.items():
        if not isinstance(word, str) or not isinstance(indexes, list):
            continue
        positions.extend((index, word) for index in indexes if isinstance(index, int))
    positions.sort()
    return " ".join(word for _index, word in positions) or None


def canonical_work_key(work: ScholarlyWorkData) -> str:
    if work.doi:
        return "doi:" + hashlib.sha256(work.doi.lower().encode()).hexdigest()
    if work.arxiv_id:
        return f"arxiv:{work.arxiv_id.lower()}"
    seed = f"{work.provider}|{work.provider_id}"
    return "provider:" + hashlib.sha256(seed.encode()).hexdigest()


def normalize_doi(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return re.sub(
        r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)",
        "",
        value.strip(),
        flags=re.I,
    ).rstrip(".").lower() or None


def normalize_arxiv(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    cleaned = re.sub(r"^(?:https?://arxiv\.org/(?:abs|pdf)/|arxiv:\s*)", "", value.strip(), flags=re.I)
    cleaned = re.sub(r"\.pdf$", "", cleaned, flags=re.I)
    return re.sub(r"v\d+$", "", cleaned) or None


def normalize_title(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def query_tokens(value: str) -> list[str]:
    stopwords = {
        "about", "after", "also", "among", "been", "from", "have", "into",
        "introduction", "model", "models", "more", "paper", "previous", "public",
        "related", "report", "reports", "result", "results", "section", "study",
        "studies", "system", "systems", "that", "their", "these", "this", "those",
        "using", "were", "which", "with", "work", "would", "benchmark", "benchmarks",
    }
    tokens = [token for token in normalize_title(value).split() if len(token) >= 4]
    return list(dict.fromkeys(token for token in tokens if token not in stopwords))


def lexical_score(query: str, record: ScholarlyWorkRecord) -> float:
    tokens = set(query_tokens(query))
    if not tokens:
        return 0.0
    title_tokens = set(query_tokens(record.title))
    abstract_tokens = set(query_tokens(record.abstract or ""))
    title_overlap = len(tokens & title_tokens) / max(len(title_tokens), 1)
    abstract_overlap = len(tokens & abstract_tokens) / len(tokens)
    return round(min(1.0, title_overlap * 0.65 + abstract_overlap * 0.35), 4)


def scholarly_work_provenance(record: ScholarlyWorkRecord) -> dict[str, Any]:
    """Project canonical fields back to the independent provider payloads."""
    provider_works = [
        work
        for provider, payload in record.provider_payloads.items()
        for work in works_from_response(provider, payload)
        if work.provider_id == record.provider_ids.get(provider)
    ]
    abstract_providers = sorted(
        work.provider
        for work in provider_works
        if work.abstract
        and record.abstract
        and " ".join(work.abstract.split()) == " ".join(record.abstract.split())
    )
    identifiers: dict[str, dict[str, Any]] = {}
    for name, value, attribute in (
        ("doi", record.doi, "doi"),
        ("arxiv", record.arxiv_id, "arxiv_id"),
    ):
        if not value:
            continue
        suppliers = sorted(
            work.provider
            for work in provider_works
            if getattr(work, attribute) == value
        )
        identifiers[name] = {"value": value, "providers": suppliers}
    return {
        "abstractProviders": abstract_providers,
        "identifiers": identifiers,
        "providerMatches": {
            work.provider: {
                "providerId": work.provider_id,
                "title": work.title,
                "year": work.year,
                "abstract": work.abstract,
                "doi": work.doi,
                "arxivId": work.arxiv_id,
                "sourceUrl": work.landing_page_url,
            }
            for work in provider_works
        },
    }


def as_int(value: Any) -> int | None:
    return value if isinstance(value, int) else None
