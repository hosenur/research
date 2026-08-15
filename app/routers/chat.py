from typing import Annotated

import httpx
from openai import AsyncOpenAI
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from fastapi.responses import StreamingResponse

from app.config import (
    OPENAI_TIMEOUT_SECONDS,
    OPENALEX_TIMEOUT_SECONDS,
    SEMANTIC_SCHOLAR_TIMEOUT_SECONDS,
    openalex_api_key,
    openalex_mailto,
    openalex_proxy,
    openalex_url,
    openai_api_key,
    openai_base_url,
    openai_chat_model,
    semantic_scholar_api_key,
    semantic_scholar_url,
    source_verification_model,
)
from app.schemas.chat import PaperChatRequest
from app.services.paper_chat import PaperChatService
from app.database.models import ChatMessageRecord
from app.database.session import get_session_factory
from app.repositories.openalex import OpenAlexRepository
from app.repositories.scholarly_works import ScholarlyWorkRepository
from app.repositories.semantic_scholar import SemanticScholarRepository
from app.services.citation_actions import CitationActionService
from app.services.manuscript_revisions import ManuscriptEditPlanner
from app.services.source_search import CitationSourceSearcher, SourceSupportVerifier

router = APIRouter(prefix="/chat", tags=["chat"])


async def get_paper_chat_service():
    mailto = openalex_mailto()
    openalex_headers = {
        "User-Agent": (
            f"folio-paper-parser (mailto:{mailto})"
            if mailto
            else "folio-paper-parser/0.1"
        )
    }
    semantic_headers = {}
    if semantic_scholar_api_key():
        semantic_headers["x-api-key"] = semantic_scholar_api_key()
    async with (
        AsyncOpenAI(
            api_key=openai_api_key(),
            base_url=openai_base_url(),
            timeout=OPENAI_TIMEOUT_SECONDS,
        ) as client,
        httpx.AsyncClient(
            base_url=openalex_url(),
            timeout=OPENALEX_TIMEOUT_SECONDS,
            headers=openalex_headers,
            proxy=openalex_proxy(),
        ) as openalex_client,
        httpx.AsyncClient(
            base_url=semantic_scholar_url(),
            timeout=SEMANTIC_SCHOLAR_TIMEOUT_SECONDS,
            headers=semantic_headers,
        ) as semantic_client,
    ):
        session_factory = get_session_factory()
        works = ScholarlyWorkRepository(session_factory)
        searcher = CitationSourceSearcher(
            works,
            OpenAlexRepository(
                openalex_client,
                mailto=mailto,
                api_key=openalex_api_key(),
                cache=works,
            ),
            SemanticScholarRepository(semantic_client, works),
        )
        verifier = SourceSupportVerifier(
            client,
            api_key=openai_api_key(),
            model=source_verification_model(),
        )
        planner = ManuscriptEditPlanner(
            client,
            api_key=openai_api_key(),
            model=openai_chat_model(),
        )
        yield PaperChatService(
            client,
            api_key=openai_api_key(),
            model=openai_chat_model(),
            citation_actions=CitationActionService(
                session_factory,
                searcher,
                verifier,
                planner,
            ),
        )


PaperAgent = Annotated[PaperChatService, Depends(get_paper_chat_service)]


@router.post("")
async def chat_with_paper(
    request: PaperChatRequest,
    agent: PaperAgent,
    paper_id: str | None = Query(default=None),
) -> StreamingResponse:
    if not agent.configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The paper agent is not configured. Set OPENAI_API_KEY on the API service.",
        )
    return StreamingResponse(
        agent.stream(request, route_paper_id=paper_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{thread_id}")
async def get_chat_thread(
    thread_id: str,
    paper_id: str | None = Query(default=None),
) -> dict[str, object]:
    async with get_session_factory()() as session:
        statement = select(ChatMessageRecord).where(ChatMessageRecord.thread_id == thread_id).order_by(ChatMessageRecord.sequence)
        if paper_id:
            statement = statement.where(ChatMessageRecord.paper_id == paper_id)
        messages = list(await session.scalars(statement))
    return {"threadId": thread_id, "messages": [{"id": message.id, "role": message.role, "content": message.content} for message in messages]}
