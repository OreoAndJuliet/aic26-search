from abc import ABC, abstractmethod


class CacheBackend(ABC):
    """Minimal cache contract with a Redis-compatible surface."""

    @abstractmethod
    def get(self, key: str) -> bytes | None:
        """Return cached bytes or None on miss."""

    @abstractmethod
    def set(self, key: str, value: bytes, *, ttl_seconds: int | None = None) -> None:
        """Store bytes with an optional TTL."""

    @abstractmethod
    def delete(self, key: str) -> None:
        """Remove one cache entry."""

    @abstractmethod
    def clear(self) -> None:
        """Remove all entries in this backend namespace."""
