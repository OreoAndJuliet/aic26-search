"""Simple Milvus connectivity check - no collection requirement."""
import sys
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import settings


def main() -> int:
    try:
        from pymilvus import MilvusClient
    except ImportError:
        print("ERROR: pymilvus is not installed")
        return 2

    milvus_uri = settings.MILVUS_URI

    try:
        client = MilvusClient(uri=milvus_uri, timeout=settings.MILVUS_TIMEOUT_SECONDS)
        # Just test connectivity by listing collections
        collections = client.list_collections()
        print("Milvus server is running. Existing collections: " + str(len(collections)))
        return 0
    except (ConnectionError, OSError, TimeoutError) as e:
        print("ERROR: could not connect to Milvus: " + str(e))
        return 3
    except Exception as e:  # noqa: BLE001 - CLI boundary: surface any unexpected error
        print("ERROR: " + str(e))
        return 1


if __name__ == "__main__":
    sys.exit(main())
