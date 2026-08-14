from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.exceptions import (
    AppError,
    ExtractionArtifactNotFoundError,
    FileTooLargeError,
    GrobidBusyError,
    GrobidEmptyResultError,
    GrobidNoTextError,
    GrobidRequestError,
    GrobidUnavailableError,
    InvalidDocumentError,
    OcrFailedError,
    PaperDocumentNotFoundError,
    PaperDocumentNotReadyError,
    UnsupportedMediaTypeError,
)

_STATUS_CODES: dict[type[AppError], int] = {
    FileTooLargeError: status.HTTP_413_CONTENT_TOO_LARGE,
    UnsupportedMediaTypeError: status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
    InvalidDocumentError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    OcrFailedError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    GrobidUnavailableError: status.HTTP_503_SERVICE_UNAVAILABLE,
    GrobidBusyError: status.HTTP_503_SERVICE_UNAVAILABLE,
    GrobidRequestError: status.HTTP_502_BAD_GATEWAY,
    GrobidNoTextError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    GrobidEmptyResultError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    ExtractionArtifactNotFoundError: status.HTTP_404_NOT_FOUND,
    PaperDocumentNotFoundError: status.HTTP_404_NOT_FOUND,
    PaperDocumentNotReadyError: status.HTTP_409_CONFLICT,
}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
        status_code = _STATUS_CODES.get(
            type(exc),
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
        return JSONResponse(
            status_code=status_code,
            content={
                "detail": exc.detail,
                "code": exc.code,
                "retryable": exc.retryable,
                "context": exc.context,
            },
        )
