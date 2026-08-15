import asyncio

from app.workers.citation_audit import run as run_citation_audit
from app.workers.reference_evidence import run as run_reference_evidence
from app.workers.source_search import run as run_source_search
from app.workers.paper_index import run as run_paper_index
from app.workers.paper_parse import run as run_paper_parse
from app.workers.quick_read import run as run_quick_read
from app.workers.existing_citations import run as run_existing_citations
from app.workers.paper_export import run as run_paper_export


async def run() -> None:
    await asyncio.gather(
        run_paper_parse(),
        run_quick_read(),
        run_existing_citations(),
        run_paper_export(),
        run_reference_evidence(),
        run_citation_audit(),
        run_source_search(),
        run_paper_index(),
    )


if __name__ == "__main__":
    asyncio.run(run())
