from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


@dataclass(frozen=True)
class VectorSearchHit:
    vector_id: int
    raw_score: float
    # provenance sources for this hit; e.g. ('faiss',), ('milvus',), ('faiss','milvus')
    sources: tuple[str, ...] = ()


@dataclass(frozen=True)
class VectorStoreStats:
    dimension: int
    vector_count: int
    metadata_count: int

class VectorStore(ABC):
    @property
    @abstractmethod
    def stats(self) -> VectorStoreStats:
        """Return immutable index statistics."""

    @abstractmethod
    def search(self, query_vector: np.ndarray, top_k: int) -> list[VectorSearchHit]:
        """Search one normalized query vector."""

    @abstractmethod
    def search_batch(
        self, query_vectors: np.ndarray, top_k: int
    ) -> list[list[VectorSearchHit]]:
        """Search a batch of normalized query vectors."""


class KeyframeVectorStore(VectorStore):
    """Vector store with keyframe metadata lookups used by KIS."""

    @abstractmethod
    def metadata_for(self, vector_id: int) -> dict[str, Any]:
        """Return metadata row for a vector id."""

    @abstractmethod
    def image_path_for_frame(self, video_id: str, frame_id: int) -> Path | None:
        """Resolve on-disk keyframe image path."""

    def reconstruct(self, vector_id: int) -> np.ndarray:
        """Return stored embedding for self-check paths."""
        raise NotImplementedError(f"{self.__class__.__name__} does not support vector reconstruction.")
