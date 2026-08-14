from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import httpx
from openai import AsyncOpenAI
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from pgvector.sqlalchemy import Vector

from app.database.models import PaperChunkRecord
from app.schemas.paper import Paper
from app.services.citation_audit import render_paragraph

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


def chunk_paper(paper: Paper) -> list[PaperChunk]:
    chunks: list[PaperChunk] = []
    if paper.abstract:
        chunks.append(PaperChunk("abstract", "abstract", paper.abstract, None, "Abstract", None))
    for section in paper.sections:
        for paragraph in section.paragraphs:
            text = render_paragraph(paragraph).strip()
            if not text:
                continue
            for index in range(0, len(text), MAX_CHUNK_CHARACTERS):
                chunks.append(PaperChunk(f"paragraph:{paragraph.id}:{index}", "paragraph", text[index:index + MAX_CHUNK_CHARACTERS], section.id, section.title, None))
    for reference in paper.references:
        chunks.append(PaperChunk(f"reference:{reference.id}", "reference", reference.raw_text, None, "References", reference.id))
    return chunks


class PaperIndexer:
    def __init__(self, client: AsyncOpenAI, *, api_key: str | None, model: str = EMBEDDING_MODEL) -> None:
        self.client, self.api_key, self.model = client, api_key, model

    async def index(self, session: AsyncSession, paper_id: str, paper: Paper) -> int:
        if not self.api_key:
            return 0
        chunks = chunk_paper(paper)
        response = await self.client.embeddings.create(model=self.model, input=[chunk.text for chunk in chunks], dimensions=EMBEDDING_DIMENSIONS)
        embeddings = response.data
        await session.execute(delete(PaperChunkRecord).where(PaperChunkRecord.paper_id == paper_id))
        for order, (chunk, embedding) in enumerate(zip(chunks, embeddings, strict=False)):
            session.add(PaperChunkRecord(id=str(uuid.uuid4()), paper_id=paper_id, chunk_key=chunk.key, chunk_type=chunk.kind, section_id=chunk.section_id, section_title=chunk.section_title, reference_id=chunk.reference_id, text=chunk.text, chunk_order=order, embedding=embedding.embedding))
        await session.commit()
        return len(embeddings)


async def search_paper_chunks(session: AsyncSession, paper_id: str, embedding: list[float], limit: int = 8) -> list[dict[str, Any]]:
    distance = PaperChunkRecord.embedding.cosine_distance(embedding).label("distance")
    rows = await session.execute(select(PaperChunkRecord, distance).where(PaperChunkRecord.paper_id == paper_id).order_by(distance).limit(limit))
    return [{"text": chunk.text, "sectionId": chunk.section_id, "sectionTitle": chunk.section_title, "referenceId": chunk.reference_id, "score": round(1 - float(distance_value), 4)} for chunk, distance_value in rows.tuples()]
