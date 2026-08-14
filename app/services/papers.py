from app.config import MAX_PDF_SIZE, MAX_TEI_SIZE
from app.exceptions import (
    FileTooLargeError,
    InvalidDocumentError,
    UnsupportedMediaTypeError,
)
from app.repositories.grobid import GrobidRepository
from app.schemas.paper import Paper
from app.services.tei_parser import TEIParseError, parse_tei


class PaperService:
    """Orchestrates PDF → GROBID → Paper JSON."""

    def __init__(self, grobid: GrobidRepository) -> None:
        self._grobid = grobid

    async def parse_pdf(self, content: bytes, filename: str) -> Paper:
        pdf = validate_pdf(content)
        tei = await self._grobid.process_fulltext(pdf, filename)
        return normalize_tei(tei)


def validate_pdf(content: bytes) -> bytes:
    if len(content) > MAX_PDF_SIZE:
        raise FileTooLargeError("PDF files must be 50 MB or smaller.")
    if not content.startswith(b"%PDF-"):
        raise UnsupportedMediaTypeError("The uploaded file is not a valid PDF.")
    return content


def normalize_tei(xml: bytes) -> Paper:
    if len(xml) > MAX_TEI_SIZE:
        raise FileTooLargeError("TEI XML files must be 100 MB or smaller.")
    if not xml.strip():
        raise InvalidDocumentError("The TEI XML file is empty.")
    try:
        return parse_tei(xml)
    except TEIParseError as exc:
        raise InvalidDocumentError(str(exc)) from exc
