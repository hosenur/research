import asyncio

from app.workers.citation_audit import run as run_citation_audit
from app.workers.openalex import run as run_openalex
from app.workers.source_search import run as run_source_search
from app.workers.paper_index import run as run_paper_index
from app.workers.paper_parse import run as run_paper_parse


async def run() -> None:
    await asyncio.gather(
        run_paper_parse(),
        run_openalex(),
        run_citation_audit(),
        run_source_search(),
        run_paper_index(),
    )


if __name__ == "__main__":
    asyncio.run(run())
