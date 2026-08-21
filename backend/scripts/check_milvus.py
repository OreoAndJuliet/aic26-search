"""Check Milvus availability and collection health for hybrid retrieval.

Usage:
  python scripts/check_milvus.py

Exits with code 0 when Milvus is reachable and collection exists and has a positive entity count.
Prints JSON status to stdout. Handles missing pymilvus gracefully.
"""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

# Add project root to sys.path
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import settings

# Use Milvus URI from configuration
milvus_uri = settings.MILVUS_URI


def main() -> int:
    result = {
        "status": "unknown",
        "milvus_uri": settings.MILVUS_URI,
        "collection": settings.MILVUS_COLLECTION,
        "entity_count": None,
        "dimension": None,
        "error": None,
    }

    try:
        try:
            from pymilvus import MilvusClient
        except ImportError:
            result["status"] = "missing_dependency"
            result["error"] = "pymilvus not installed"
            print(json.dumps(result, indent=2))
            return 2

        # Connect using modern MilvusClient API
        try:
            client = MilvusClient(
                uri=milvus_uri,
                timeout=settings.MILVUS_TIMEOUT_SECONDS
            )
        except (ConnectionError, OSError, TimeoutError) as exc:
            result["status"] = "unreachable"
            result["error"] = f"could not connect to Milvus at {settings.MILVUS_URI}: {exc}"
            print(json.dumps(result, indent=2))
            return 3

        # Check collection using modern API
        try:
            if not client.has_collection(settings.MILVUS_COLLECTION):
                result["status"] = "missing_collection"
                result["error"] = f"collection {settings.MILVUS_COLLECTION} not found"
                print(json.dumps(result, indent=2))
                return 4

            # Get collection info
            collection_info = client.get_collection_stats(settings.MILVUS_COLLECTION)
            entity_count = collection_info.get("row_count", 0)
            result["entity_count"] = entity_count

            # Get collection schema for vector dimension
            collection_schema = client.describe_collection(settings.MILVUS_COLLECTION)
            vector_field = next(
                (f for f in collection_schema.get("fields", []) if f.get("type") in [101, "FloatVector", "Float32Vector"]),
                None,
            )
            if vector_field is None:
                result["status"] = "invalid_schema"
                result["error"] = "no FloatVector field found"
                print(json.dumps(result, indent=2))
                return 5

            dim = vector_field.get("params", {}).get("dim", 0)
            result["dimension"] = dim

            if entity_count <= 0:
                result["status"] = "empty_collection"
                print(json.dumps(result, indent=2))
                return 6

            result["status"] = "ok"
            print(json.dumps(result, indent=2))
            return 0

        except Exception as exc:  # noqa: BLE001 - runtime boundary: surface unexpected API errors
            result["status"] = "error"
            result["error"] = str(exc)
            result["trace"] = traceback.format_exc()
            print(json.dumps(result, indent=2))
            return 7

    except Exception as exc:  # pragma: no cover - defensive  # noqa: BLE001
        print(json.dumps({"status": "fatal", "error": str(exc), "trace": traceback.format_exc()}, indent=2))
        return 10


if __name__ == "__main__":
    raise SystemExit(main())
