class AppError(Exception):
    """Expected application failure with a public error message."""

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


class FileTooLargeError(AppError):
    pass


class UnsupportedMediaTypeError(AppError):
    pass


class InvalidDocumentError(AppError):
    pass


class GrobidUnavailableError(AppError):
    pass


class GrobidRequestError(AppError):
    pass
