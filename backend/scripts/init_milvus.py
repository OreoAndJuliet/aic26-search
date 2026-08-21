"""Initialize Milvus collection for hybrid retrieval.

Usage:
  python scripts/init_milvus.py

This script creates the Milvus collection if it doesn't exist and optionally
syncs FAISS vectors into it.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add project root to sys.path
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import settings

# Use Milvus URI from configuration
milvus_uri = settings.MILVUS_URI


def init_collection(collection_name: str, dimension: int = 512) -> None:
    """Initialize Milvus collection with specified dimension and create index."""
    try:
        from pymilvus import MilvusClient
    except ImportError:
        print("ERROR: pymilvus not installed. Run: pip install pymilvus")
        sys.exit(1)

    try:
        client = MilvusClient(uri=milvus_uri)
        print(f"Connected to Milvus at {milvus_uri}")
        
        if client.has_collection(collection_name):
            print(f"Collection '{collection_name}' already exists")
            stats = client.get_collection_stats(collection_name)
            print(f"  Entity count: {stats.get('row_count', 0)}")
            return
        
        print(f"Creating collection '{collection_name}' with dimension {dimension}")
        # Use modern API with 'embedding' field name to match application expectations
        # Modern API creates index automatically
        client.create_collection(
            collection_name=collection_name,
            dimension=dimension,
            primary_field_name="vector_id",
            auto_id=False,
            metric_type="IP",
            consistency_level="Strong"
        )
        print(f"Collection '{collection_name}' created successfully")
        print("Index created automatically on vector field")
        
    except Exception as e:  # noqa: BLE001 - CLI boundary: report runtime errors to operator
        print(f"ERROR: Failed to initialize collection: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize Milvus collection")
    parser.add_argument("--collection", default=settings.MILVUS_COLLECTION, help="Collection name")
    parser.add_argument("--dimension", type=int, default=512, help="Vector dimension")
    parser.add_argument("--sync", action="store_true", help="Sync FAISS vectors after initialization")
    args = parser.parse_args()
    
    init_collection(args.collection, args.dimension)
    
    if args.sync:
        print("\nSyncing FAISS vectors to Milvus...")
        from scripts.sync_milvus import sync_milvus
        
        index_path = Path(settings.FAISS_INDEX_PATH)
        metadata_path = Path(settings.METADATA_PATH)
        
        if not index_path.exists():
            print(f"ERROR: FAISS index not found at {index_path}")
            print("Run build_index.py first to create the index")
            sys.exit(1)
            
        if not metadata_path.exists():
            print(f"ERROR: Metadata not found at {metadata_path}")
            sys.exit(1)
        
        count = sync_milvus(
            index_path=index_path,
            metadata_path=metadata_path,
            collection_name=args.collection,
        )
        print(f"Synced {count} vectors to Milvus")


if __name__ == "__main__":
    main()
