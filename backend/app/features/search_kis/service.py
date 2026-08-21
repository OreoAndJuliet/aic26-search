import logging
import time
from uuid import uuid4

from app.core.config import settings
from app.core.exceptions import InvalidQueryError
from app.features.search.contract import normalize_search_results
from app.features.search.retrieval import run_kis_retrieval
from app.services.translator import translator

logger = logging.getLogger(__name__)


async def run_kis_search(
    text: str, top_k: int = 20, request_id: str | None = None
) -> dict:
    """Run the KIS pipeline and report stage timing without logging query text."""
    if not text.strip():
        raise InvalidQueryError("Query text cannot be blank.")

    request_id = request_id or uuid4().hex
    started_at = time.perf_counter()
    translation = await translator.translate_async(text)
    translation_time_ms = round((time.perf_counter() - started_at) * 1000, 2)

    results, metrics = run_kis_retrieval(translation.text, top_k)
    total_time_ms = round((time.perf_counter() - started_at) * 1000, 2)

    response = {
        "status": "success",
        "request_id": request_id,
        "query": text,
        "translated_query": translation.text,
        "translated_text": translation.text,
        "translation_applied": translation.applied,
        "results": normalize_search_results(
            results,
            backend_host=settings.BACKEND_HOST,
            default_answer=None,
        ),
        "rscore": metrics["rscore"],
        "translation_time_ms": translation_time_ms,
        "embedding_time_ms": metrics["embedding_time_ms"],
        "faiss_time_ms": metrics["faiss_time_ms"],
        "metadata_time_ms": metrics["metadata_time_ms"],
        "retrieval_time_ms": metrics["retrieval_time_ms"],
        "total_time_ms": total_time_ms,
        "latency_ms": total_time_ms,
    }
    logger.info(
        "request_id=%s endpoint=/api/v1/search/kis total_time_ms=%s "
        "translation_time_ms=%s embedding_time_ms=%s faiss_time_ms=%s metadata_time_ms=%s "
        "result_count=%s text_encoder_provider=%s translation_provider=%s",
        request_id,
        total_time_ms,
        translation_time_ms,
        metrics["embedding_time_ms"],
        metrics["faiss_time_ms"],
        metrics["metadata_time_ms"],
        len(results),
        settings.TEXT_ENCODER_PROVIDER,
        translator.provider_name,
    )
    return response
