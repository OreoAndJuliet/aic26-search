"""Hybrid FAISS + Milvus retrieval with reciprocal-rank fusion."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from app.vector.base import KeyframeVectorStore, VectorSearchHit, VectorStoreStats
from app.vector.faiss_store import FaissVectorStore
from app.vector.merge import merge_hits_rrf
from app.vector.milvus_store import MilvusVectorStore


class HybridVectorStore(KeyframeVectorStore):
    """Query FAISS locally and Milvus remotely, then fuse ranked lists."""

    def __init__(
        self,
        faiss_store: FaissVectorStore,
        milvus_store: MilvusVectorStore | None,
        *,
        rrf_k: int = 60,
    ) -> None:
        self._faiss = faiss_store
        self._milvus = milvus_store
        self._rrf_k = rrf_k

    @property
    def stats(self) -> VectorStoreStats:
        return self._faiss.stats

    def metadata_for(self, vector_id: int) -> dict[str, Any]:
        return self._faiss.metadata_for(vector_id)

    def image_path_for_frame(self, video_id: str, frame_id: int) -> Path | None:
        return self._faiss.image_path_for_frame(video_id, frame_id)

    def reconstruct(self, vector_id: int) -> np.ndarray:
        return self._faiss.reconstruct(vector_id)

    def search(self, query_vector: np.ndarray, top_k: int) -> list[VectorSearchHit]:
        faiss_hits = self._faiss.search(query_vector, top_k)
        # annotate faiss-only hits if milvus isn't available
        if self._milvus is None:
            return [
                VectorSearchHit(vector_id=h.vector_id, raw_score=h.raw_score, sources=("faiss",))
                for h in faiss_hits
            ]
        try:
            milvus_hits = self._milvus.search(query_vector, top_k)
        except Exception:
            return [
                VectorSearchHit(vector_id=h.vector_id, raw_score=h.raw_score, sources=("faiss",))
                for h in faiss_hits
            ]
        fused = merge_hits_rrf(faiss_hits, milvus_hits, top_k=top_k, rrf_k=self._rrf_k)
        # build id sets for provenance mapping
        faiss_ids = {h.vector_id for h in faiss_hits}
        milvus_ids = {h.vector_id for h in milvus_hits}
        annotated: list[VectorSearchHit] = []
        for h in fused:
            sources = tuple(s for s, idset in (("faiss", faiss_ids), ("milvus", milvus_ids)) if h.vector_id in idset)
            if not sources:
                sources = ("unknown",)
            annotated.append(VectorSearchHit(vector_id=h.vector_id, raw_score=h.raw_score, sources=sources))
        return annotated

    def search_batch(
        self, query_vectors: np.ndarray, top_k: int
    ) -> list[list[VectorSearchHit]]:
        faiss_batches = self._faiss.search_batch(query_vectors, top_k)
        # annotate faiss-only batches when milvus isn't enabled
        if self._milvus is None:
            return [
                [VectorSearchHit(vector_id=h.vector_id, raw_score=h.raw_score, sources=("faiss",)) for h in batch]
                for batch in faiss_batches
            ]
        try:
            milvus_batches = self._milvus.search_batch(query_vectors, top_k)
        except Exception:
            return [
                [VectorSearchHit(vector_id=h.vector_id, raw_score=h.raw_score, sources=("faiss",)) for h in batch]
                for batch in faiss_batches
            ]
        annotated_batches: list[list[VectorSearchHit]] = []
        for faiss_hits, milvus_hits in zip(faiss_batches, milvus_batches, strict=True):
            fused = merge_hits_rrf(faiss_hits, milvus_hits, top_k=top_k, rrf_k=self._rrf_k)
            faiss_ids = {h.vector_id for h in faiss_hits}
            milvus_ids = {h.vector_id for h in milvus_hits}
            annotated = []
            for h in fused:
                sources = tuple(s for s, idset in (("faiss", faiss_ids), ("milvus", milvus_ids)) if h.vector_id in idset)
                if not sources:
                    sources = ("unknown",)
                annotated.append(VectorSearchHit(vector_id=h.vector_id, raw_score=h.raw_score, sources=sources))
            annotated_batches.append(annotated)
        return annotated_batches
