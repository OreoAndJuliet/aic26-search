class BackendError(Exception):
    """Base exception that is safe to expose through the API."""

    code = "BACKEND_ERROR"
    status_code = 500

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InvalidQueryError(BackendError):
    code = "INVALID_QUERY"
    status_code = 422


class EmbeddingDimensionMismatchError(BackendError):
    code = "EMBEDDING_DIMENSION_MISMATCH"
    status_code = 422


class RetrievalUnavailableError(BackendError):
    code = "RETRIEVAL_UNAVAILABLE"
    status_code = 503


class RetrievalFailedError(BackendError):
    code = "RETRIEVAL_FAILED"
    status_code = 500


class DatasetValidationError(BackendError):
    code = "DATASET_INVALID"
    status_code = 503


class TranslationUnavailableError(BackendError):
    code = "TRANSLATION_UNAVAILABLE"
    status_code = 503


class VLMUnavailableError(BackendError):
    code = "VLM_UNAVAILABLE"
    status_code = 503


class CacheUnavailableError(BackendError):
    code = "CACHE_UNAVAILABLE"
    status_code = 503
