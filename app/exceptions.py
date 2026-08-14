class AppError(Exception):
    """Expected application failure with a public error message."""

    code = "application_error"
    retryable = False

    def __init__(self, detail: str, *, context: dict[str, object] | None = None) -> None:
        self.detail = detail
        self.context = context or {}
        super().__init__(detail)


class FileTooLargeError(AppError):
    pass


class UnsupportedMediaTypeError(AppError):
    pass


class InvalidDocumentError(AppError):
    pass


class OcrFailedError(InvalidDocumentError):
    code = "ocr_failed"


class GrobidUnavailableError(AppError):
    code = "grobid_unavailable"
    retryable = True


class GrobidRequestError(AppError):
    code = "grobid_request_failed"


class GrobidBusyError(GrobidUnavailableError):
    code = "grobid_busy"


class GrobidNoTextError(GrobidRequestError):
    code = "grobid_no_text"


class GrobidEmptyResultError(GrobidRequestError):
    code = "grobid_empty_result"


class ExtractionArtifactNotFoundError(AppError):
    code = "extraction_artifact_not_found"


class PaperDocumentNotFoundError(AppError):
    code = "paper_document_not_found"
