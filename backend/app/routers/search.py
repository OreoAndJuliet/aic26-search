import logging
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from app.core.exceptions import BackendError
from app.features.search.schemas import SearchRequest
from app.features.search.service import run_search
from app.features.search_kis.schemas import KisSearchRequest, KisSearchResponse
from app.features.search_kis.service import run_kis_search

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/search")
async def search(req: SearchRequest):
    """
    Unified search endpoint as required by AIC 2026 specification.
    Handles KIS, VQA, and TRAKE via the type field.
    Endpoint: POST /api/search (with prefix="/api" in main.py)
    """
    request_id = uuid4().hex
    try:
        return await run_search(
            task_type=req.type,
            query=req.display_query(),
            question=req.question,
            top_k=req.top_k,
            events=req.events if req.type == "TRAKE" else None,
            top_k_per_event=req.top_k_per_event,
            max_gap_seconds=req.max_gap_seconds,
            video_filter=req.video_filter,
            request_id=request_id,
        )
    except BackendError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except Exception as exc:
        import traceback
        with open("error_log.txt", "a") as f:
            f.write(f"Search endpoint exception: {exc}\n")
            f.write(traceback.format_exc() + "\n")
        logger.exception("runtime error while handling /api/search request_id=%s", request_id)
        raise HTTPException(status_code=500, detail=f"runtime_error: {exc}") from exc


@router.post("/search_trake")
async def search_trake(req: SearchRequest):
    """
    TRAKE-specific endpoint as required by AIC 2026 specification.
    Endpoint: POST /api/search_trake (with prefix="/api" in main.py)
    This provides a dedicated endpoint for temporal retrieval and alignment of key events.
    The functionality is identical to using type="TRAKE" in the unified search endpoint.
    """
    request_id = uuid4().hex
    try:
        return await run_search(
            task_type="TRAKE",
            query=req.display_query(),
            question=req.question,
            top_k=req.top_k,
            events=req.events,
            top_k_per_event=req.top_k_per_event,
            max_gap_seconds=req.max_gap_seconds,
            request_id=request_id,
        )
    except BackendError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except RuntimeError as exc:
        logger.exception("runtime error while handling /api/search_trake request_id=%s", request_id)
        raise HTTPException(status_code=503, detail=f"runtime_error: {exc}") from exc


@router.post("/v1/search/kis", response_model=KisSearchResponse)
async def search_kis(req: KisSearchRequest):
    """Backward compatibility endpoint for version 1 API."""
    return await run_kis_search(req.query, req.top_k)


@router.post("/v1/search")
async def search_v1(req: SearchRequest):
    """Backward compatibility endpoint for version 1 API."""
    request_id = uuid4().hex
    try:
        return await run_search(
            task_type=req.type,
            query=req.display_query(),
            question=req.question,
            top_k=req.top_k,
            events=req.events if req.type == "TRAKE" else None,
            top_k_per_event=req.top_k_per_event,
            max_gap_seconds=req.max_gap_seconds,
            request_id=request_id,
        )
    except BackendError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except RuntimeError as exc:
        logger.exception("runtime error while handling /api/v1/search request_id=%s", request_id)
        raise HTTPException(status_code=503, detail=f"runtime_error: {exc}") from exc
