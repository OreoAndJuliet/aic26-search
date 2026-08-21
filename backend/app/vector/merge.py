"""Merge vector search hits from multiple backends."""

from __future__ import annotations

from app.vector.base import VectorSearchHit


def merge_hits_rrf(
    *hit_lists: list[VectorSearchHit],
    top_k: int,
    rrf_k: int = 60,
) -> list[VectorSearchHit]:
    """Reciprocal-rank fusion across one or more ranked hit lists."""
    if top_k <= 0:
        return []

    fused_scores: dict[int, float] = {}
    for hits in hit_lists:
        for rank, hit in enumerate(hits):
            fused_scores[hit.vector_id] = fused_scores.get(hit.vector_id, 0.0) + (
                1.0 / (rrf_k + rank + 1)
            )

    ranked_ids = sorted(fused_scores, key=fused_scores.get, reverse=True)[:top_k]
    return [
        VectorSearchHit(vector_id=vector_id, raw_score=round(fused_scores[vector_id], 6))
        for vector_id in ranked_ids
    ]
