from fastapi import APIRouter

from app.core.exceptions import RetrievalUnavailableError
from app.services.kis_engine import kis_engine

router = APIRouter()


@router.get("/health")
def health() -> dict:
    """Health check endpoint at root level."""
    try:
        stats = kis_engine.stats
    except RetrievalUnavailableError:
        return {"status": "degraded", "kis": "unavailable"}

    # Include circuit breaker status if available
    circuit_status = {}
    try:
        from app.utils.circuit_breaker import get_all_circuit_breaker_statuses
        circuit_status = get_all_circuit_breaker_statuses()
    except ImportError:
        # Circuit breaker module not available
        pass

    return {
        "status": "ok",
        "kis": "ready",
        "vector_count": stats.vector_count,
        "circuit_breakers": circuit_status
    }


@router.get("/api/health")
def health_api() -> dict:
    """Health check endpoint at /api/health for AIC 2026 specification."""
    return health()


@router.get("/api/v1/system/info")
def system_info() -> dict:
    stats = kis_engine.stats
    return {
        "kis": {
            "vector_count": stats.vector_count,
            "metadata_count": stats.metadata_count,
            "dimension": stats.dimension,
            "similarity": "cosine (normalized inner product)",
        }
    }


@router.get("/api/v1/system/circuit-breakers")
def circuit_breakers_status() -> dict:
    """Get detailed status of all circuit breakers."""
    try:
        from app.utils.circuit_breaker import get_all_circuit_breaker_statuses
        return get_all_circuit_breaker_statuses()
    except ImportError:
        return {"error": "Circuit breaker module not available"}
