from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile

from app.config import MAX_PDF_SIZE, MAX_TEI_SIZE
from app.dependencies import get_missing_work_finder, get_openalex_enricher, get_paper_service
from app.schemas.paper import MissingWorkReport, Paper
from app.services.missing_works import MissingWorkFinder
from app.services.openalex import OpenAlexEnricher
from app.services.papers import PaperService, normalize_tei

router = APIRouter(prefix="/papers", tags=["papers"])

PdfUpload = Annotated[UploadFile, File(description="Academic paper in PDF format")]
TeiUpload = Annotated[UploadFile, File(description="GROBID TEI XML document")]
PaperParser = Annotated[PaperService, Depends(get_paper_service)]
ReferenceEnricher = Annotated[OpenAlexEnricher, Depends(get_openalex_enricher)]
MissingWorks = Annotated[MissingWorkFinder, Depends(get_missing_work_finder)]


@router.post("/parse", response_model=Paper)
async def parse_paper(file: PdfUpload, service: PaperParser) -> Paper:
    """Parse an uploaded academic paper into the normalized Paper model."""
    content = await file.read(MAX_PDF_SIZE + 1)
    return await service.parse_pdf(content, file.filename or "paper.pdf")


@router.post("/normalize", response_model=Paper)
async def normalize_paper(file: TeiUpload) -> Paper:
    """Normalize an existing GROBID TEI XML document into the internal Paper model."""
    xml = await file.read(MAX_TEI_SIZE + 1)
    return normalize_tei(xml)


@router.post("/enrich", response_model=Paper)
async def enrich_paper(paper: Paper, enricher: ReferenceEnricher) -> Paper:
    """Look up parsed references on OpenAlex. Misses stay unmatched."""
    return await enricher.enrich_paper(paper)


@router.post("/missing-works", response_model=MissingWorkReport)
async def find_missing_works(paper: Paper, finder: MissingWorks) -> MissingWorkReport:
    """Search OpenAlex for related work that is not already in the bibliography."""
    return await finder.find(paper)
