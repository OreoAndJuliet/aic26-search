from app.cache.base import CacheBackend
from app.core.exceptions import CacheUnavailableError


class RedisCacheBackend(CacheBackend):
    """Redis-backed cache. Requires the optional `redis` package."""

    def __init__(
        self,
        *,
        namespace: str,
        url: str,
        max_entries: int,
        client: object | None = None,
    ) -> None:
        try:
            import redis
        except ImportError as exc:
            raise CacheUnavailableError(
                "Redis cache backend requires the `redis` package. Install it with: pip install redis"
            ) from exc

        if not url.strip():
            raise CacheUnavailableError("REDIS_URL is required when CACHE_BACKEND=redis.")

        self._namespace = namespace.strip() or "default"
        self._max_entries = max_entries
        self._client = client or redis.Redis.from_url(url, decode_responses=False)

    def _namespaced_key(self, key: str) -> str:
        return f"{self._namespace}:{key}"

    def get(self, key: str) -> bytes | None:
        value = self._client.get(self._namespaced_key(key))
        if value is None:
            return None
        return bytes(value)

    def set(self, key: str, value: bytes, *, ttl_seconds: int | None = None) -> None:
        namespaced = self._namespaced_key(key)
        if ttl_seconds is not None and ttl_seconds > 0:
            self._client.setex(namespaced, ttl_seconds, value)
        else:
            self._client.set(namespaced, value)
        self._enforce_max_entries()

    def delete(self, key: str) -> None:
        self._client.delete(self._namespaced_key(key))

    def clear(self) -> None:
        pattern = f"{self._namespace}:*"
        cursor = 0
        while True:
            cursor, keys = self._client.scan(cursor=cursor, match=pattern, count=256)
            if keys:
                self._client.delete(*keys)
            if cursor == 0:
                break

    def _enforce_max_entries(self) -> None:
        pattern = f"{self._namespace}:*"
        cursor = 0
        keys: list[bytes] = []
        while True:
            cursor, batch = self._client.scan(cursor=cursor, match=pattern, count=256)
            keys.extend(batch)
            if cursor == 0:
                break
        overflow = len(keys) - self._max_entries
        if overflow <= 0:
            return
        for key in keys[:overflow]:
            self._client.delete(key)
