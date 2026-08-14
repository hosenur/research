import httpx

from app.exceptions import GrobidRequestError, GrobidUnavailableError


class GrobidRepository:
    """Talks to GROBID's full-text processing API."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def process_fulltext(self, pdf: bytes, filename: str) -> bytes:
        try:
            response = await self._client.post(
                "/api/processFulltextDocument",
                files={"input": (filename, pdf, "application/pdf")},
                data={
                    "consolidateHeader": "0",
                    "consolidateCitations": "0",
                    "includeRawCitations": "1",
                },
            )
        except httpx.RequestError as exc:
            raise GrobidUnavailableError("The GROBID service is unavailable.") from exc

        if response.status_code != 200:
            error_message = response.text.strip()[:500]
            detail = f"GROBID returned HTTP {response.status_code}."
            if error_message:
                detail = f"{detail} {error_message}"
            raise GrobidRequestError(detail)

        return response.content
