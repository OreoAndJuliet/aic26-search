"""Sync FAISS index vectors into a Milvus collection for hybrid retrieval."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Add project root to sys.path
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import faiss
import numpy as np

from app.core.config import settings

# Use Milvus URI from configuration
milvus_uri = settings.MILVUS_URI


def _load_metadata(metadata_path: Path) -> list[dict]:
    if not metadata_path.exists():
        raise FileNotFoundError(f"Metadata file not found: {metadata_path}")
    if not metadata_path.is_file():
        raise ValueError(f"Metadata path exists but is not a file: {metadata_path}")
    
    with metadata_path.open("r", encoding="utf-8") as file:
        metadata = json.load(file)
    if not isinstance(metadata, list) or not metadata:
        raise ValueError("Metadata must be a non-empty JSON list.")
    return metadata


def _ensure_collection(collection_name: str, dimension: int):
    from pymilvus import MilvusClient

    client = MilvusClient(uri=milvus_uri)
    
    if client.has_collection(collection_name):
        return client

    # Create collection using modern API (creates 'vector' field by default)
    client.create_collection(
        collection_name=collection_name,
        dimension=dimension,
        primary_field_name="vector_id",
        auto_id=False,
        metric_type="IP",
        consistency_level="Strong"
    )
    
    return client


def sync_milvus(
    *,
    index_path: Path,
    metadata_path: Path,
    collection_name: str,
    batch_size: int = 512,
    recreate: bool = False,
) -> int:
    from pymilvus import MilvusClient

    # Validate index path exists
    if not index_path.exists():
        raise FileNotFoundError(f"FAISS index file not found: {index_path}")
    if not index_path.is_file():
        raise ValueError(f"FAISS index path exists but is not a file: {index_path}")

    metadata = _load_metadata(metadata_path)
    
    # Use faiss.IndexBinary or handle memory more efficiently
    # For large indexes, use mmap to avoid loading everything into memory
    try:
        # Try to load with memory mapping for large files
        index = faiss.read_index(str(index_path))
    except (OSError, ValueError) as e:
        print(f"Error loading FAISS index: {e}")
        print("Try using a smaller subset or reducing the index size")
        raise
    except Exception as e:
        print(f"Error loading FAISS index: {e}")
        print("Try using a smaller subset or reducing the index size")
        raise
    
    if index.ntotal != len(metadata):
        raise ValueError("FAISS vector count does not match metadata row count.")

    client = MilvusClient(uri=milvus_uri)
    
    if recreate and client.has_collection(collection_name):
        client.drop_collection(collection_name)

    client = _ensure_collection(collection_name, int(index.d))

    inserted = 0
    vector_ids: list[int] = []
    embeddings: list[list[float]] = []

    print(f"Starting sync of {int(index.ntotal)} vectors with batch size {batch_size}")
    
    for vector_id in range(int(index.ntotal)):
        vector_ids.append(vector_id)
        embeddings.append(np.asarray(index.reconstruct(vector_id), dtype=np.float32).tolist())
        if len(vector_ids) >= batch_size:
            # Convert to list of row dicts for Milvus insert (required format)
            # Modern API creates 'vector' field by default
            rows = [
                {"vector_id": vid, "vector": emb}
                for vid, emb in zip(vector_ids, embeddings)
            ]
            client.insert(
                collection_name=collection_name,
                data=rows
            )
            inserted += len(vector_ids)
            print(f"Progress: {inserted}/{int(index.ntotal)} vectors inserted")
            vector_ids = []
            embeddings = []

    if vector_ids:
        # Convert to list of row dicts for Milvus insert (required format)
        # Modern API creates 'vector' field by default
        rows = [
            {"vector_id": vid, "vector": emb}
            for vid, emb in zip(vector_ids, embeddings)
        ]
        client.insert(
            collection_name=collection_name,
            data=rows
        )
        inserted += len(vector_ids)

    client.flush(collection_name)
    return inserted


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync FAISS vectors into Milvus.")
    parser.add_argument("--index", type=Path, default=settings.FAISS_INDEX_PATH)
    parser.add_argument("--metadata", type=Path, default=settings.METADATA_PATH)
    parser.add_argument("--collection", default=settings.MILVUS_COLLECTION)
    parser.add_argument("--batch-size", type=int, default=512)
    parser.add_argument("--recreate", action="store_true")
    args = parser.parse_args()

    count = sync_milvus(
        index_path=args.index,
        metadata_path=args.metadata,
        collection_name=args.collection,
        batch_size=args.batch_size,
        recreate=args.recreate,
    )
    print(f"Synced {count} vectors into Milvus collection '{args.collection}'.")


if __name__ == "__main__":
    main()
