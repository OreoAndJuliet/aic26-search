import time
from collections import OrderedDict
from dataclasses import dataclass
from threading import Lock

from app.cache.base import CacheBackend


@dataclass(frozen=True)
class _MemoryEntry:
    value: bytes
    expires_at: float | None


class MemoryCacheBackend(CacheBackend):
    """Thread-safe in-memory LRU cache."""

    def __init__(self, *, namespace: str, max_entries: int) -> None:
        if max_entries <= 0:
            raise ValueError("max_entries must be positive.")
        self._namespace = namespace.strip() or "default"
        self._max_entries = max_entries
        self._entries: OrderedDict[str, _MemoryEntry] = OrderedDict()
        self._lock = Lock()

    def _namespaced_key(self, key: str) -> str:
        return f"{self._namespace}:{key}"

    def _purge_expired(self, entry: _MemoryEntry) -> bool:
        if entry.expires_at is None:
            return False
        return entry.expires_at <= time.monotonic()

    def get(self, key: str) -> bytes | None:
        namespaced = self._namespaced_key(key)
        with self._lock:
            entry = self._entries.get(namespaced)
            if entry is None:
                return None
            if self._purge_expired(entry):
                self._entries.pop(namespaced, None)
                return None
            self._entries.move_to_end(namespaced)
            return entry.value

    def set(self, key: str, value: bytes, *, ttl_seconds: int | None = None) -> None:
        namespaced = self._namespaced_key(key)
        expires_at = None
        if ttl_seconds is not None and ttl_seconds > 0:
            expires_at = time.monotonic() + ttl_seconds

        with self._lock:
            self._entries[namespaced] = _MemoryEntry(value=value, expires_at=expires_at)
            self._entries.move_to_end(namespaced)
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)

    def delete(self, key: str) -> None:
        namespaced = self._namespaced_key(key)
        with self._lock:
            self._entries.pop(namespaced, None)

    def clear(self) -> None:
        with self._lock:
            prefix = f"{self._namespace}:"
            for key in list(self._entries.keys()):
                if key.startswith(prefix):
                    self._entries.pop(key, None)
