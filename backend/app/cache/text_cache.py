from app.cache.base import CacheBackend
from app.cache.keys import build_translation_cache_key


class TextCache:
    """Caches UTF-8 text payloads such as translated queries."""

    def __init__(
        self,
        backend: CacheBackend,
        *,
        source_language: str,
        target_language: str,
        ttl_seconds: int | None = None,
    ) -> None:
        self._backend = backend
        self._source_language = source_language
        self._target_language = target_language
        self._ttl_seconds = ttl_seconds

    def _key(self, text: str) -> str:
        return build_translation_cache_key(
            source_language=self._source_language,
            target_language=self._target_language,
            text=text,
        )

    def get(self, text: str) -> str | None:
        payload = self._backend.get(self._key(text))
        if payload is None:
            return None
        return payload.decode("utf-8")

    def set(self, text: str, value: str) -> None:
        self._backend.set(
            self._key(text),
            value.encode("utf-8"),
            ttl_seconds=self._ttl_seconds,
        )

    def clear(self) -> None:
        self._backend.clear()
