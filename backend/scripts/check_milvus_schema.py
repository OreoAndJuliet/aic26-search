"""Check Milvus collection schema."""
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

        client = MilvusClient(uri=milvus_uri)
        collection_name = settings.MILVUS_COLLECTION

        print(f"Connected to Milvus at {milvus_uri}")
        print(f"Collection: {collection_name}")

        stats = client.get_collection_stats(collection_name)
        print(f"Entity count: {stats.get('row_count', 0)}")

        schema = client.describe_collection(collection_name)
        print(f"Fields: {[f.get('name') for f in schema.get('fields', [])]}")

        for field in schema.get("fields", []):
            print(f"  Field: {field.get('name')}, Type: {field.get('type')}")
            if field.get("type") in ("FloatVector", 101):
                print(f"    Dimension: {field.get('params', {}).get('dim', 0)}")
        return 0

    except ImportError:
        print("ERROR: pymilvus is not installed")
        return 2
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
