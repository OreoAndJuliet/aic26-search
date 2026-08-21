"""Fix Milvus collection by dropping and recreating with proper index."""

import sys
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import settings


def main() -> int:
    milvus_uri = settings.MILVUS_URI

    try:
        from pymilvus import MilvusClient
    except ImportError:
        print("ERROR: pymilvus is not installed")
        return 2

    try:
        client = MilvusClient(uri=milvus_uri)
        collection_name = settings.MILVUS_COLLECTION

        print(f"Connected to Milvus at {milvus_uri}")
        print(f"Target collection: {collection_name}")

        if client.has_collection(collection_name):
            print(f"Dropping existing collection '{collection_name}'...")
            client.drop_collection(collection_name)
            print("Collection dropped successfully")
        else:
            print(f"Collection '{collection_name}' does not exist")

        print("\nNow run: python scripts\\init_milvus.py --sync")
        print("This will recreate the collection with proper index and sync vectors")
        return 0
    except (ConnectionError, OSError, TimeoutError) as e:
        print(f"ERROR: could not connect to Milvus: {e}")
        return 3
    except Exception as e:  # noqa: BLE001 - CLI boundary: surface unexpected runtime errors
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
