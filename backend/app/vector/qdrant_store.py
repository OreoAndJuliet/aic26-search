"""Qdrant vector store backed by the shared metadata catalog."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from app.core.exceptions import (
    InvalidQueryError,
    RetrievalUnavailableError,
)
from app.vector.base import KeyframeVectorStore, VectorSearchHit, VectorStoreStats
from app.vector.metadata_catalog import MetadataCatalog


class QdrantVectorStore(KeyframeVectorStore):
    """Remote Qdrant collection keyed by vector_id with shared metadata.json."""

    def __init__(
        self,
        metadata_path: Path,
        *,
        url: str,
        collection_name: str,
        api_key: str | None = None,
        timeout_seconds: float = 5.0,
    ) -> None:
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import Distance, PointStruct, VectorParams
        except ImportError as exc:
            raise RetrievalUnavailableError(
                "Qdrant backend requires the qdrant-client package."
            ) from exc

        self._catalog = MetadataCatalog(metadata_path)
        self._url = url.strip()
        self._collection_name = collection_name.strip()
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds

        if not self._url:
            raise RetrievalUnavailableError("QDRANT_URL is not configured.")
        if not self._collection_name:
            raise RetrievalUnavailableError("QDRANT_COLLECTION is not configured.")

        # Initialize Qdrant client
        if self._api_key:
            self._client = QdrantClient(
                url=self._url,
                api_key=self._api_key,
                timeout=self._timeout_seconds,
            )
        else:
            self._client = QdrantClient(
                url=self._url,
                timeout=self._timeout_seconds,
            )

        # Validate collection exists
        try:
            collections = self._client.get_collections()
            collection_names = [c.name for c in collections.collections]
            if self._collection_name not in collection_names:
                raise RetrievalUnavailableError(
                    f"Qdrant collection '{self._collection_name}' does not exist. "
                    f"Available collections: {collection_names}"
                )
        except Exception as exc:
            raise RetrievalUnavailableError(
                f"Failed to connect to Qdrant or validate collection: {exc}"
            ) from exc

    @property
    def stats(self) -> VectorStoreStats:
        """Return immutable index statistics."""
        try:
            collection_info = self._client.get_collection(self._collection_name)
            vector_count = collection_info.points_count
            dimension = collection_info.config.params.vectors.size
            metadata_count = self._catalog.metadata_count
            return VectorStoreStats(
                dimension=dimension,
                vector_count=vector_count,
                metadata_count=metadata_count,
            )
        except Exception as exc:
            raise RetrievalUnavailableError(
                f"Failed to get Qdrant collection stats: {exc}"
            ) from exc

    def search(self, query_vector: np.ndarray, top_k: int) -> list[VectorSearchHit]:
        """Search one normalized query vector."""
        if query_vector.ndim != 1:
            raise InvalidQueryError("Query vector must be 1-dimensional")

        try:
            vec_list = query_vector.tolist()
            if hasattr(self._client, "query_points"):
                response = self._client.query_points(
                    collection_name=self._collection_name,
                    query=vec_list,
                    limit=top_k,
                    with_payload=True,
                )
                points = response.points if hasattr(response, "points") else response
            elif hasattr(self._client, "search"):
                points = self._client.search(
                    collection_name=self._collection_name,
                    query_vector=vec_list,
                    limit=top_k,
                    with_payload=True,
                )
            else:
                raise RetrievalUnavailableError("QdrantClient does not provide query_points or search methods.")

            hits = []
            for result in points:
                vector_id = result.id
                score = result.score
                hits.append(
                    VectorSearchHit(
                        vector_id=int(vector_id),
                        raw_score=float(score),
                        sources=("qdrant",),
                    )
                )
            return hits

        except Exception as exc:
            raise RetrievalUnavailableError(f"Qdrant search failed: {exc}") from exc

    def search_batch(
        self, query_vectors: np.ndarray, top_k: int
    ) -> list[list[VectorSearchHit]]:
        """Search a batch of normalized query vectors."""
        if query_vectors.ndim != 2:
            raise InvalidQueryError("Query vectors must be 2-dimensional")

        try:
            batch_hits = []
            for v in query_vectors:
                batch_hits.append(self.search(v, top_k))
            return batch_hits

        except Exception as exc:
            raise RetrievalUnavailableError(f"Qdrant batch search failed: {exc}") from exc

    def metadata_for(self, vector_id: int) -> dict[str, Any]:
        """Return metadata row for a vector id."""
        return self._catalog.metadata_for(vector_id)

    def image_path_for_frame(self, video_id: str, frame_id: int) -> Path | None:
        """Resolve on-disk keyframe image path."""
        return self._catalog.image_path_for_frame(video_id, frame_id)