from __future__ import annotations

import asyncio

from bullmq import Job, Worker
from openai import AsyncOpenAI

from app.config import (
    CLAIM_CITATION_REVIEW_QUEUE_NAME,
    OPENAI_TIMEOUT_SECONDS,
    bullmq_options,
    openai_api_key,
    openai_base_url,
    source_verification_model,
)
from app.database.session import get_session_factory
from app.repositories.claim_citations import ClaimCitationReviewRepository
from app.repositories.papers import PaperDocumentRepository
from app.repositories.pipeline import PaperPipelineRepository
from app.database.models import PaperRecord
from app.services.claim_citation_review import ClaimCitationReviewer


async def run() -> None:
    async with AsyncOpenAI(
        api_key=openai_api_key(),
        base_url=openai_base_url(),
        timeout=OPENAI_TIMEOUT_SECONDS,
    ) as client:
        reviewer = ClaimCitationReviewer(
            client,
            api_key=openai_api_key(),
            model=source_verification_model(),
        )

        async def process(job: Job, _token: str) -> dict[str, int]:
            paper_id = str(job.data.get("paperId") or "")
            section_ids = [
                str(value) for value in (job.data.get("sectionIds") or []) if value
            ]
            if not paper_id:
                raise ValueError("The claim-citation-review job is missing paperId.")
            try:
                async with get_session_factory()() as session:
                    pipeline = PaperPipelineRepository(session)
                    await pipeline.begin(paper_id, "existing-citation-review")
                    document = await PaperDocumentRepository(session).get(paper_id)
                    paper_record = await session.get(PaperRecord, paper_id)
                    manuscript_revision = (
                        paper_record.manuscript_revision if paper_record else document.revision
                    )
                    paper = document.paper
                    if section_ids:
                        allowed = set(section_ids)
                        paper = paper.model_copy(
                            update={"sections": [
                                section for section in paper.sections if section.id in allowed
                            ]}
                        )
                    count = await reviewer.review(
                        ClaimCitationReviewRepository(session),
                        paper_id,
                        paper,
                        revision=manuscript_revision,
                    )
                async with get_session_factory()() as session:
                    await PaperPipelineRepository(session).complete(
                        paper_id,
                        "existing-citation-review",
                        revision=manuscript_revision,
                        progress={"pairs": count},
                    )
                return {"pairs": count}
            except Exception as exc:
                async with get_session_factory()() as session:
                    await PaperPipelineRepository(session).fail(
                        paper_id, "existing-citation-review", str(exc)
                    )
                raise

        worker = Worker(
            CLAIM_CITATION_REVIEW_QUEUE_NAME,
            process,
            {**bullmq_options(), "autorun": False, "concurrency": 1},
        )
        await worker.run()


if __name__ == "__main__":
    asyncio.run(run())
