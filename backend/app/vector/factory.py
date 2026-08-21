"""Create the configured keyframe vector store backend."""

from __future__ import annotations

import logging

from app.core.config import settings
from app.core.exceptions import RetrievalUnavailableError
from app.vector.base import KeyframeVectorStore
from app.vector.faiss_store import FaissVectorStore
from app.vector.hybrid_store import HybridVectorStore
from app.vector.milvus_store import MilvusVectorStore
from app.vector.qdrant_store import QdrantVectorStore

# Try to import MilvusException for proper error handling
try:
    from pymilvus.exceptions import MilvusException
    MILVUS_EXCEPTIONS = (MilvusException, RetrievalUnavailableError, OSError)
except ImportError:
    MILVUS_EXCEPTIONS = (RetrievalUnavailableError, OSError)

logger = logging.getLogger(__name__)


def create_vector_store() -> KeyframeVectorStore:
    backend = settings.VECTOR_BACKEND.strip().lower()
    faiss_store = FaissVectorStore(settings.FAISS_INDEX_PATH, settings.METADATA_PATH)

    if backend == "faiss":
        return faiss_store

    if backend == "milvus":
        return MilvusVectorStore(
            settings.METADATA_PATH,
            uri=settings.MILVUS_URI,
            collection_name=settings.MILVUS_COLLECTION,
            timeout_seconds=settings.MILVUS_TIMEOUT_SECONDS,
        )

    if backend == "qdrant":
        qdrant_url = getattr(settings, "QDRANT_URL", None)
        qdrant_api_key = getattr(settings, "QDRANT_API_KEY", None)
        qdrant_collection = getattr(settings, "QDRANT_COLLECTION", "aic_keyframes")
        qdrant_timeout = getattr(settings, "QDRANT_TIMEOUT_SECONDS", 5.0)

        if not qdrant_url:
            raise RetrievalUnavailableError("QDRANT_URL is not configured.")

        return QdrantVectorStore(
            settings.METADATA_PATH,
            url=qdrant_url,
            collection_name=qdrant_collection,
            api_key=qdrant_api_key,
            timeout_seconds=qdrant_timeout,
        )

    if backend == "hybrid":
        milvus_store: MilvusVectorStore | None
        try:
            milvus_store = MilvusVectorStore(
                settings.METADATA_PATH,
                uri=settings.MILVUS_URI,
                collection_name=settings.MILVUS_COLLECTION,
                timeout_seconds=settings.MILVUS_TIMEOUT_SECONDS,
            )
        except MILVUS_EXCEPTIONS as exc:
            logger.warning("hybrid_milvus_unavailable falling back to faiss-only: %s", exc)
            milvus_store = None
        return HybridVectorStore(
            faiss_store,
            milvus_store,
            rrf_k=settings.HYBRID_RRF_K,
        )

    raise RetrievalUnavailableError(f"Unsupported vector backend: {settings.VECTOR_BACKEND}.")
