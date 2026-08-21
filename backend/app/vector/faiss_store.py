from pathlib import Path
from typing import Any

import faiss
import numpy as np

from app.core.exceptions import (
    DatasetValidationError,
    EmbeddingDimensionMismatchError,
    InvalidQueryError,
)
from app.vector.base import KeyframeVectorStore, VectorSearchHit, VectorStoreStats
from app.vector.metadata_catalog import MetadataCatalog


class FaissVectorStore(KeyframeVectorStore):
    """Read-only FAISS index with validated, position-stable metadata."""

    def __init__(self, index_path: Path, metadata_path: Path) -> None:
        self._index_path = Path(index_path)
        self._metadata_path = Path(metadata_path)
        self._catalog = MetadataCatalog(self._metadata_path)
        self._index = self._read_index()
        self._catalog.validate_vector_count(int(self._index.ntotal))

    @property
    def stats(self) -> VectorStoreStats:
        return VectorStoreStats(
            dimension=int(self._index.d),
            vector_count=int(self._index.ntotal),
            metadata_count=self._catalog.metadata_count,
        )

    @property
    def metadata(self) -> tuple[dict[str, Any], ...]:
        return self._catalog.metadata

    def metadata_for(self, vector_id: int) -> dict[str, Any]:
        return self._catalog.metadata_for(vector_id)

    def image_path_for_frame(self, video_id: str, frame_id: int) -> Path | None:
        return self._catalog.image_path_for_frame(video_id, frame_id)

    def reconstruct(self, vector_id: int) -> np.ndarray:
        if not 0 <= vector_id < self._index.ntotal:
            raise DatasetValidationError("Vector ID is outside the FAISS index.")
        return np.asarray(self._index.reconstruct(int(vector_id)), dtype=np.float32)

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
        if vectors.shape[1] != self._index.d:
            raise EmbeddingDimensionMismatchError(
                f"Query embedding dimension {vectors.shape[1]} does not match index dimension {self._index.d}."
            )
        if not np.isfinite(vectors).all():
            raise InvalidQueryError("Query embedding contains invalid numeric values.")
        if top_k < 1:
            raise InvalidQueryError("top_k must be at least 1.")
        effective_top_k = min(top_k, int(self._index.ntotal))

        scores, vector_ids = self._index.search(vectors, effective_top_k)
        batches: list[list[VectorSearchHit]] = []
        for row_scores, row_ids in zip(scores, vector_ids, strict=True):
            hits: list[VectorSearchHit] = []
            for score, vector_id in zip(row_scores, row_ids, strict=True):
                if not 0 <= int(vector_id) < self._catalog.metadata_count:
                    raise DatasetValidationError("FAISS returned an ID without metadata.")
                hits.append(VectorSearchHit(vector_id=int(vector_id), raw_score=float(score)))
            batches.append(hits)
        return batches

    def _read_index(self) -> faiss.Index:
        if not self._index_path.is_file():
            raise DatasetValidationError("FAISS index file is missing.")
        try:
            index = faiss.read_index(str(self._index_path))
        except (OSError, ValueError) as exc:
            raise DatasetValidationError("FAISS index file is invalid or corrupted.") from exc
        except Exception as exc:  # faiss does not expose a stable exception hierarchy; noqa: BLE001
            raise DatasetValidationError("FAISS index file is invalid or corrupted.") from exc
        if index.ntotal <= 0 or index.d <= 0:
            raise DatasetValidationError("FAISS index is empty or has an invalid dimension.")
        return index
