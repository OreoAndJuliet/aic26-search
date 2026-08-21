"""Milvus vector store backed by the shared metadata catalog."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from app.core.exceptions import (
    DatasetValidationError,
    EmbeddingDimensionMismatchError,
    InvalidQueryError,
    RetrievalUnavailableError,
)
from app.vector.base import KeyframeVectorStore, VectorSearchHit, VectorStoreStats
from app.vector.metadata_catalog import MetadataCatalog


class MilvusVectorStore(KeyframeVectorStore):
    """Remote Milvus collection keyed by vector_id with shared metadata.json."""

    def __init__(
        self,
        metadata_path: Path,
        *,
        uri: str,
        collection_name: str,
        timeout_seconds: float = 5.0,
    ) -> None:
        try:
            from pymilvus import MilvusClient
        except ImportError as exc:
            raise RetrievalUnavailableError(
                "Milvus backend requires the pymilvus package."
            ) from exc

        self._catalog = MetadataCatalog(metadata_path)
        self._uri = uri.strip()
        self._collection_name = collection_name.strip()
        self._timeout_seconds = timeout_seconds

        if not self._uri:
            raise RetrievalUnavailableError("MILVUS_URI is not configured.")
        if not self._collection_name:
            raise RetrievalUnavailableError("MILVUS_COLLECTION is not configured.")

        # Use modern MilvusClient API
        self._client = MilvusClient(uri=self._uri, timeout=self._timeout_seconds)
        
        if not self._client.has_collection(self._collection_name):
            raise RetrievalUnavailableError(
                f"Milvus collection '{self._collection_name}' was not found."
            )

        # Get collection stats
        stats = self._client.get_collection_stats(self._collection_name)
        try:
            entity_count = int(stats.get("row_count", 0))
        except (ValueError, TypeError):
            entity_count = 0
        if entity_count <= 0:
            raise DatasetValidationError("Milvus collection is empty.")
        self._catalog.validate_vector_count(entity_count)

        # Get collection schema to find vector field
        collection_schema = self._client.describe_collection(self._collection_name)
        vector_field = next(
            (f for f in collection_schema.get("fields", []) if f.get("type") in [101, "FloatVector", "Float32Vector"]),  # FloatVector type codes
            None,
        )
        if vector_field is None:
            raise DatasetValidationError("Milvus collection is missing a float vector field.")
        
        # Modern API creates 'vector' field by default
        self._vector_field_name = vector_field.get("name", "vector")
        self._dimension = vector_field.get("params", {}).get("dim", 0)

    @property
    def stats(self) -> VectorStoreStats:
        stats = self._client.get_collection_stats(self._collection_name)
        return VectorStoreStats(
            dimension=self._dimension,
            vector_count=stats.get("row_count", 0),
            metadata_count=self._catalog.metadata_count,
        )

    def metadata_for(self, vector_id: int) -> dict[str, Any]:
        return self._catalog.metadata_for(vector_id)

    def image_path_for_frame(self, video_id: str, frame_id: int) -> Path | None:
        return self._catalog.image_path_for_frame(video_id, frame_id)

    def reconstruct(self, vector_id: int) -> np.ndarray:
        # Use modern MilvusClient query API with configured vector field
        field_name = getattr(self, "_vector_field_name", "vector")
        rows = self._client.query(
            collection_name=self._collection_name,
            filter=f"vector_id == {int(vector_id)}",
            output_fields=[field_name],
        )
        if not rows:
            raise DatasetValidationError("Milvus returned no vector for the requested ID.")
        raw_vec = rows[0].get(field_name) or rows[0].get("vector")
        if raw_vec is None:
            raise DatasetValidationError("Milvus row missing vector data.")
        vector = np.asarray(raw_vec, dtype=np.float32).reshape(-1)
        if vector.shape[0] != self._dimension:
            raise EmbeddingDimensionMismatchError(
                f"Milvus vector dimension {vector.shape[0]} does not match {self._dimension}."
            )
        return vector

    def search(self, query_vector: np.ndarray, top_k: int) -> list[VectorSearchHit]:
        vector = np.asarray(query_vector, dtype=np.float32)
        if vector.ndim != 1:
            raise InvalidQueryError("Single-vector search requires a one-dimensional embedding.")
        return self.search_batch(vector.reshape(1, -1), top_k)[0]

    def search_batch(
        self, query_vectors: np.ndarray, top_k: int
    ) -> list[list[VectorSearchHit]]:
        vectors = np.asarray(query_vectors, dtype=np.float32)
        if vectors.ndim != 2:
            raise InvalidQueryError("Query embeddings must be a two-dimensional array.")
        if vectors.shape[1] != self._dimension:
            raise EmbeddingDimensionMismatchError(
                f"Query embedding dimension {vectors.shape[1]} does not match collection dimension {self._dimension}."
            )
        if not np.isfinite(vectors).all():
            raise InvalidQueryError("Query embedding contains invalid numeric values.")
        if top_k < 1:
            raise InvalidQueryError("top_k must be at least 1.")
        
        effective_limit = min(top_k, max(1, self.stats.vector_count))

        # Use modern MilvusClient search API (uses default vector field)
        search_result = self._client.search(
            collection_name=self._collection_name,
            data=vectors.tolist(),
            limit=effective_limit,
            output_fields=["vector_id"],
        )

        batches: list[list[VectorSearchHit]] = []
        for hits in search_result:
            row: list[VectorSearchHit] = []
            for hit in hits:
                raw_id = hit.get("id")
                if raw_id is None:
                    raw_id = hit.get("entity", {}).get("vector_id")
                if raw_id is not None:
                    vector_id = int(raw_id)
                    row.append(VectorSearchHit(vector_id=vector_id, raw_score=float(hit.get("distance", 0.0))))
            batches.append(row)
        return batches
