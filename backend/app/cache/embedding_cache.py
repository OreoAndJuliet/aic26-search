import numpy as np

from app.cache.base import CacheBackend
from app.cache.keys import build_embedding_cache_key


class EmbeddingCache:
    """Caches text embeddings as raw float32 vectors."""

    def __init__(
        self,
        backend: CacheBackend,
        *,
        scope: str,
        ttl_seconds: int | None = None,
    ) -> None:
        self._backend = backend
        self._scope = scope
        self._ttl_seconds = ttl_seconds

    def get(self, text: str) -> np.ndarray | None:
        """Get cached embedding vector.
        
        Returns a read-only view from np.frombuffer.
        Callers that need to modify the vector must use .copy() first.
        """
        payload = self._backend.get(build_embedding_cache_key(scope=self._scope, text=text))
        if payload is None:
            return None
        vector = np.frombuffer(payload, dtype=np.float32)
        if vector.size == 0:
            return None
        return vector.reshape(-1)

    def set(self, text: str, vector: np.ndarray) -> None:
        arr = np.asarray(vector, dtype=np.float32).reshape(-1)
        self._backend.set(
            build_embedding_cache_key(scope=self._scope, text=text),
            arr.tobytes(),
            ttl_seconds=self._ttl_seconds,
        )

    def clear(self) -> None:
        self._backend.clear()
