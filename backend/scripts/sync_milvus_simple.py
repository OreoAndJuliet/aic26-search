"""Simple Milvus sync using smaller batches to avoid memory issues."""

import sys
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import faiss
import numpy as np

from app.core.config import settings

# Use Milvus URI from configuration
milvus_uri = settings.MILVUS_URI

def main():
    try:
        from pymilvus import CollectionSchema, DataType, FieldSchema, MilvusClient
    except ImportError:
        print("ERROR: pymilvus not installed")
        sys.exit(1)

    # Check if collection exists, create if not
    client = MilvusClient(uri=milvus_uri)
    collection_name = settings.MILVUS_COLLECTION
    
    print(f"Connected to Milvus at {milvus_uri}")
    
    if not client.has_collection(collection_name):
        print(f"Creating collection '{collection_name}'...")
        fields = [
            FieldSchema(name="vector_id", dtype=DataType.INT64, is_primary=True),
            FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=512),
        ]
        schema = CollectionSchema(fields=fields, metric_type="IP", consistency_level="Strong")
        client.create_collection(collection_name=collection_name, schema=schema)
        print("Collection created (index created automatically)")
    else:
        print(f"Collection '{collection_name}' already exists")
        stats = client.get_collection_stats(collection_name)
        print(f"  Entity count: {stats.get('row_count', 0)}")
        return  # Don't sync if collection already has data

    # Load FAISS index with smaller batch processing
    index_path = Path(settings.FAISS_INDEX_PATH)
    print(f"Loading FAISS index from {index_path}")
    
    # Use faiss.IndexBinary to avoid memory issues with large indexes
    try:
        index = faiss.read_index(str(index_path))
    except (OSError, ValueError) as e:
        print(f"Error loading FAISS index: {e}")
        sys.exit(1)
    except Exception as e:  # noqa: BLE001 - unexpected faiss error
        print(f"Error loading FAISS index: {e}")
        sys.exit(1)
    
    total_vectors = int(index.ntotal)
    print(f"Total vectors: {total_vectors}")
    
    # Check current count and continue from there
    stats = client.get_collection_stats(collection_name)
    current_count = stats.get('row_count', 0)
    
    if current_count >= 1000:
        print(f"Collection already has {current_count} vectors, skipping sync")
        return
    
    # Process in batches to avoid memory issues
    batch_size = 200  # Medium batch size
    total_inserted = 0
    offset = current_count  # Continue from where we left off
    max_vectors = min(total_vectors, 5000)  # Sync up to 5000 for testing
    
    print(f"Continuing from vector {offset} to {max_vectors} in batches of {batch_size}...")
    
    vector_ids = []
    embeddings = []
    
    for vector_id in range(offset, max_vectors):
        try:
            vector = index.reconstruct(vector_id)
            vector_ids.append(vector_id)
            embeddings.append(np.asarray(vector, dtype=np.float32).tolist())
            
            if len(vector_ids) >= batch_size:
                rows = [{"vector_id": vid, "embedding": emb} for vid, emb in zip(vector_ids, embeddings)]
                client.insert(collection_name=collection_name, data=rows)
                total_inserted += len(vector_ids)
                print(f"Progress: {offset + total_inserted}/{max_vectors} vectors inserted")
                vector_ids = []
                embeddings = []
                
        except (IndexError, OSError, ValueError) as e:
            print(f"Error processing vector {vector_id}: {e}")
            continue
        except Exception as e:  # noqa: BLE001 - unexpected vector reconstruction error
            print(f"Error processing vector {vector_id}: {e}")
            continue
    
    # Insert remaining
    if vector_ids:
        rows = [{"vector_id": vid, "embedding": emb} for vid, emb in zip(vector_ids, embeddings)]
        client.insert(collection_name=collection_name, data=rows)
        total_inserted += len(vector_ids)
    
    final_total = offset + total_inserted
    print(f"Successfully synced {total_inserted} additional vectors to Milvus")
    print(f"Total vectors in Milvus: {final_total}/{total_vectors}")
    print(f"Note: For production, sync all {total_vectors} vectors")

if __name__ == "__main__":
    main()
