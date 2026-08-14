from __future__ import annotations

import asyncio
from openai import AsyncOpenAI
from bullmq import Job, Queue, Worker

from app.config import OPENAI_TIMEOUT_SECONDS, PAPER_INDEX_QUEUE_NAME, bullmq_options, openai_api_key, openai_base_url
from app.database.session import get_session_factory
from app.repositories.papers import PaperDocumentRepository
from app.services.paper_index import PaperIndexer


async def run() -> None:
    async with AsyncOpenAI(api_key=openai_api_key(), base_url=openai_base_url(), timeout=OPENAI_TIMEOUT_SECONDS) as client:
        indexer = PaperIndexer(client, api_key=openai_api_key())

        async def process(job: Job, _token: str) -> dict[str, int]:
            paper_id = str(job.data.get("paperId") or "")
            if not paper_id:
                raise ValueError("The paper-index job is missing paperId.")
            async with get_session_factory()() as session:
                document = await PaperDocumentRepository(session).get(paper_id)
                count = await indexer.index(session, paper_id, document.paper)
                return {"chunks": count}

        worker = Worker(PAPER_INDEX_QUEUE_NAME, process, {**bullmq_options(), "autorun": False, "concurrency": 1})
        await worker.run()


if __name__ == "__main__":
    asyncio.run(run())
