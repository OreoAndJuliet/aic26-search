from app.cache.base import CacheBackend
from app.cache.memory import MemoryCacheBackend
from app.cache.redis_backend import RedisCacheBackend
from app.core.config import settings


def create_cache_backend(*, namespace: str) -> CacheBackend:
    backend = settings.CACHE_BACKEND.strip().lower()
    if backend == "redis":
        return RedisCacheBackend(
            namespace=namespace,
            url=settings.REDIS_URL,
            max_entries=settings.CACHE_MAX_ENTRIES,
        )
    if backend not in {"memory", "inmemory", "local"}:
        raise ValueError(f"Unsupported CACHE_BACKEND: {settings.CACHE_BACKEND}")
    return MemoryCacheBackend(
        namespace=namespace,
        max_entries=settings.CACHE_MAX_ENTRIES,
    )
