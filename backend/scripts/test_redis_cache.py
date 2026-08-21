"""Manual Redis cache smoke test against a live Redis server."""

from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.cache.embedding_cache import EmbeddingCache
from app.cache.redis_backend import RedisCacheBackend
from app.cache.text_cache import TextCache
from app.core.exceptions import CacheUnavailableError


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test Redis cache backend.")
    parser.add_argument(
        "--url",
        default=os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0"),
        help="Redis connection URL",
    )
    args = parser.parse_args()

    try:
        backend = RedisCacheBackend(
            namespace="kis-smoke-test",
            url=args.url,
            max_entries=100,
        )
        backend._client.ping()
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        print(json.dumps({"status": "failed", "error": str(exc)}))
        return 1

    embedding_cache = EmbeddingCache(backend, scope="smoke-test:512", ttl_seconds=60)
    text_cache = TextCache(
        backend,
        source_language="vi",
        target_language="en",
        ttl_seconds=60,
    )

    vector = np.array([0.1, 0.2, 0.3, 0.4], dtype=np.float32)
    embedding_cache.set("redis smoke test", vector)
    restored = embedding_cache.get("redis smoke test")

    text_cache.set("một người", "a person")
    translated = text_cache.get("một người")

    if restored is None or not np.allclose(restored, vector):
        raise CacheUnavailableError("Embedding cache roundtrip failed.")
    if translated != "a person":
        raise CacheUnavailableError("Text cache roundtrip failed.")

    backend.clear()
    print(
        json.dumps(
            {
                "status": "ok",
                "url": args.url,
                "embedding_dim": int(restored.shape[0]),
                "translation": translated,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
