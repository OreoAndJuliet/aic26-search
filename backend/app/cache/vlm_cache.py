from app.cache.base import CacheBackend
from app.cache.keys import build_vlm_cache_key


class VlmCache:
    """Caches VLM answers keyed by (question, video_id, keyframe_id)."""

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

    def get(self, *, video_id: str, keyframe_id: int, question: str) -> str | None:
        payload = self._backend.get(
            build_vlm_cache_key(
                scope=self._scope,
                video_id=video_id,
                keyframe_id=keyframe_id,
                question=question,
            )
        )
        if payload is None:
            return None
        return payload.decode("utf-8")

    def set(
        self,
        *,
        video_id: str,
        keyframe_id: int,
        question: str,
        answer: str,
    ) -> None:
        self._backend.set(
            build_vlm_cache_key(
                scope=self._scope,
                video_id=video_id,
                keyframe_id=keyframe_id,
                question=question,
            ),
            answer.encode("utf-8"),
            ttl_seconds=self._ttl_seconds,
        )

    def clear(self) -> None:
        self._backend.clear()
