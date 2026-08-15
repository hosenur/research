from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import httpx
from openai import AsyncOpenAI
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from pgvector.sqlalchemy import Vector

from app.database.models import PaperChunkRecord
from app.schemas.paper import Paper
from app.services.citation_audit import render_paragraph
from app.services.quick_read import QuickTextChunk

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536
MAX_CHUNK_CHARACTERS = 2_400


@dataclass(frozen=True)
class PaperChunk:
    key: str
    kind: str
    text: str
    section_id: str | None
    section_title: str | None
    reference_id: str | None
    source_node_id: str | None


def chunk_paper(paper: Paper) -> list[PaperChunk]:
    chunks: list[PaperChunk] = []
    if paper.abstract:
        chunks.append(PaperChunk("abstract", "abstract", paper.abstract, None, "Abstract", None, "abstract"))
    for section in paper.sections:
        for paragraph in section.paragraphs:
            text = render_paragraph(paragraph).strip()
            if not text:
                continue
            for index in range(0, len(text), MAX_CHUNK_CHARACTERS):
                chunks.append(PaperChunk(f"paragraph:{paragraph.id}:{index}", "paragraph", text[index:index + MAX_CHUNK_CHARACTERS], section.id, section.title, None, paragraph.id))
    for reference in paper.references:
        chunks.append(PaperChunk(f"reference:{reference.id}", "reference", reference.raw_text, None, "References", reference.id, reference.id))
    return chunks


class PaperIndexer:
    def __init__(self, client: AsyncOpenAI, *, api_key: str | None, model: str = EMBEDDING_MODEL) -> None:
        self.client, self.api_key, self.model = client, api_key, model

    async def index(
        self,
        session: AsyncSession,
        paper_id: str,
        paper: Paper,
        *,
        revision: int = 1,
    ) -> int:
        return await self._index_chunks(
            session,
            paper_id,
            chunk_paper(paper),
            index_kind="authoritative",
            revision=revision,
        )

    async def index_quick_text(
        self,
        session: AsyncSession,
        paper_id: str,
        chunks: list[QuickTextChunk],
        *,
        revision: int = 1,
    ) -> int:
        projected = [
            PaperChunk(
                key=chunk.key,
                kind="provisional",
                text=chunk.text,
                section_id=None,
                section_title=None,
                reference_id=None,
                source_node_id=None,
            )
            for chunk in chunks
        ]
        return await self._index_chunks(
            session,
            paper_id,
            projected,
            index_kind="provisional",
            revision=revision,
        )

    async def _index_chunks(
        self,
        session: AsyncSession,
        paper_id: str,
        chunks: list[PaperChunk],
        *,
        index_kind: str,
        revision: int,
    ) -> int:
        if not self.api_key:
            raise RuntimeError("Paper indexing requires OPENAI_API_KEY on the worker service.")
        if not chunks:
            return 0
        response = await self.client.embeddings.create(model=self.model, input=[chunk.text for chunk in chunks], dimensions=EMBEDDING_DIMENSIONS)
        embeddings = response.data
        generation = revision
        await session.execute(
            delete(PaperChunkRecord).where(
                PaperChunkRecord.paper_id == paper_id,
                PaperChunkRecord.index_kind == index_kind,
                PaperChunkRecord.generation == generation,
            )
        )
        for order, (chunk, embedding) in enumerate(zip(chunks, embeddings, strict=False)):
            session.add(PaperChunkRecord(id=str(uuid.uuid4()), paper_id=paper_id, chunk_key=chunk.key, chunk_type=chunk.kind, section_id=chunk.section_id, section_title=chunk.section_title, reference_id=chunk.reference_id, source_node_id=chunk.source_node_id, index_kind=index_kind, paper_revision=revision, generation=generation, text=chunk.text, chunk_order=order, embedding=embedding.embedding))
        await session.commit()
        return len(embeddings)


async def search_paper_chunks(session: AsyncSession, paper_id: str, embedding: list[float], limit: int = 8) -> list[dict[str, Any]]:
    index_kind = await current_index_kind(session, paper_id)
    if index_kind == "unavailable":
        return []
    generation = await session.scalar(
        select(func.max(PaperChunkRecord.generation)).where(
            PaperChunkRecord.paper_id == paper_id,
            PaperChunkRecord.index_kind == index_kind,
        )
    )
    distance = PaperChunkRecord.embedding.cosine_distance(embedding).label("distance")
    rows = await session.execute(select(PaperChunkRecord, distance).where(PaperChunkRecord.paper_id == paper_id, PaperChunkRecord.index_kind == index_kind, PaperChunkRecord.generation == generation).order_by(distance).limit(limit))
    return [{"text": chunk.text, "sectionId": chunk.section_id, "sectionTitle": chunk.section_title, "referenceId": chunk.reference_id, "sourceNodeId": chunk.source_node_id, "indexKind": chunk.index_kind, "score": round(1 - float(distance_value), 4)} for chunk, distance_value in rows.tuples()]


async def current_index_kind(session: AsyncSession, paper_id: str) -> str:
    kinds = set(
        await session.scalars(
            select(PaperChunkRecord.index_kind).where(PaperChunkRecord.paper_id == paper_id)
        )
    )
    if "authoritative" in kinds:
        return "authoritative"
    if "provisional" in kinds:
        return "provisional"
    return "unavailable"
