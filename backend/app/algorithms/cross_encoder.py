"""Lightweight cross-encoder style rescoring using reconstructed image embeddings.

This module implements a simple rescoring proxy for a cross-encoder: when enabled,
for the top-N candidates it reconstructs image embeddings from the vector store and
computes a refined cosine similarity with the query embedding, then blends that
score with the existing r_score to produce a final ranking.

It is intentionally simple and robust: if the store cannot reconstruct a vector
(for remote/missing entries), it falls back to the original score.
"""

from __future__ import annotations

import logging
import math

import numpy as np

from app.core.config import settings
from app.vector.base import KeyframeVectorStore

logger = logging.getLogger(__name__)


def _cosine(u: np.ndarray, v: np.ndarray) -> float:
    if u is None or v is None:
        return 0.0
    if u.size == 0 or v.size == 0:
        return 0.0
    du = np.linalg.norm(u)
    dv = np.linalg.norm(v)
    if du == 0 or dv == 0 or not math.isfinite(du) or not math.isfinite(dv):
        return 0.0
    return float(np.dot(u, v) / (du * dv))


def rescore_top_k(
    query_vector: np.ndarray,
    results: list[dict],
    store: KeyframeVectorStore,
    top_k: int | None = None,
) -> list[dict]:
    """Rescore the top-k results in-place (returns a new list).

    - query_vector: 1-D numpy vector for the text query
    - results: list of mapped result dicts (must include 'vector_id' and existing scores)
    - store: the KeyframeVectorStore instance to call reconstruct(vector_id)
    - top_k: how many top results to rescored; defaults to settings.CROSS_ENCODER_TOP_K
    """
    if not settings.CROSS_ENCODER_ENABLED or not results:
        return results

    k = int(top_k or settings.CROSS_ENCODER_TOP_K)
    k = max(1, min(k, len(results)))

    rescored = []
    for i, item in enumerate(results):
        # compute rescoring only for top-k, otherwise keep original
        if i < k:
            try:
                vector_id = int(item.get("vector_id") or item.get("vector_id"))
            except (TypeError, ValueError) as exc:
                logger.debug("cross_encoder: invalid vector_id for item=%s error=%s", item, exc)
                vector_id = None

            if vector_id is None:
                # cannot rescore without vector mapping — set final_score to existing score
                copy = dict(item)
                copy["final_score"] = float(copy.get("r_score", copy.get("score", 0.0)))
                rescored.append(copy)
                continue

            try:
                image_vec = store.reconstruct(vector_id)
            except (RuntimeError, OSError) as exc:
                # Reconstruction failed — set final_score to existing score (log debug)
                logger.debug("cross_encoder: reconstruct failed for vector_id=%s error=%s", vector_id, exc)
                copy = dict(item)
                copy["final_score"] = float(copy.get("r_score", copy.get("score", 0.0)))
                rescored.append(copy)
                continue

            try:
                # Ensure shapes
                qv = np.asarray(query_vector, dtype=np.float32).reshape(-1)
                iv = np.asarray(image_vec, dtype=np.float32).reshape(-1)
                cross_cos = _cosine(qv, iv)
            except (ValueError, TypeError) as exc:
                logger.debug("cross_encoder: failed to compute cosine for vector_id=%s error=%s", vector_id, exc)
                cross_cos = 0.0

            base_score = float(item.get("r_score", item.get("score", 0.0)))
            # map cross_cos (-1..1) to 0..1 like r_score
            mapped_cross = max(0.0, min(1.0, (cross_cos + 1.0) / 2.0))

            alpha = float(settings.CROSS_ENCODER_WEIGHT)
            final = round(alpha * mapped_cross + (1.0 - alpha) * base_score, 6)

            copy = dict(item)
            copy["cross_cosine"] = round(cross_cos, 6)
            copy["final_score"] = final
            rescored.append(copy)
        else:
            # keep rest unchanged
            copy = dict(item)
            copy["final_score"] = float(copy.get("r_score", copy.get("score", 0.0)))
            rescored.append(copy)

    # sort by final_score desc (then original rank)
    rescored.sort(key=lambda r: (-float(r.get("final_score", r.get("r_score", r.get("score", 0.0)))), int(r.get("rank", 999))))
    for rank, item in enumerate(rescored, start=1):
        item["rank"] = rank
    return rescored
