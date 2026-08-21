"""Visual Pseudo-Relevance Feedback (Visual PRF / Rocchio Query Expansion).

Shifts the text query embedding towards the visual centroid of top-ranking candidate frames,
closing the cross-modal semantic gap and boosting recall in visual cluster neighborhoods.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


def apply_visual_pseudo_relevance_feedback(
    candidates: list[dict[str, Any]],
    query_vector: np.ndarray,
    vector_store: Any,
    *,
    top_m_visual: int = 3,
    prf_weight: float = 0.20,
    blend_alpha: float = 0.30,
) -> list[dict[str, Any]]:
    """Re-ranks candidates using Rocchio visual query feedback from top-M frames.

    Args:
        candidates: List of candidate result dictionaries.
        query_vector: 512-dim normalized query vector.
        vector_store: Vector store with `reconstruct(vector_id)` or `_faiss_store.reconstruct`.
        top_m_visual: Number of top-ranked visual frames to construct centroid from (default: 3).
        prf_weight: Strength of visual PRF boost applied to candidate scores (default: 0.20).
        blend_alpha: Weight of the visual centroid when updating the query vector (default: 0.30).

    Returns:
        Updated candidate list re-sorted with Visual PRF scores.
    """
    if not candidates or prf_weight <= 0.0 or top_m_visual <= 0:
        return candidates

    reconstruct_fn = None
    if hasattr(vector_store, "reconstruct"):
        reconstruct_fn = vector_store.reconstruct
    elif hasattr(vector_store, "_faiss_store") and hasattr(vector_store._faiss_store, "reconstruct"):
        reconstruct_fn = vector_store._faiss_store.reconstruct

    if reconstruct_fn is None:
        return candidates

    # Ensure query vector is a 1D unit vector
    q_vec = np.asarray(query_vector).flatten().astype(np.float32)
    q_norm = np.linalg.norm(q_vec)
    if q_norm > 0:
        q_vec = q_vec / q_norm

    # 1. Collect top-M visual vectors
    visual_vectors = []
    weights = []
    eval_count = min(top_m_visual, len(candidates))

    for rank_idx in range(eval_count):
        cand = candidates[rank_idx]
        v_id = cand.get("vector_id")
        if v_id is None:
            continue
        try:
            vec = reconstruct_fn(int(v_id))
            v_norm = np.linalg.norm(vec)
            if v_norm > 0:
                vec = vec / v_norm
                # Exponential rank decay weight
                w = 1.0 / (rank_idx + 1.0)
                visual_vectors.append(vec * w)
                weights.append(w)
        except Exception as exc:
            logger.debug("Failed to reconstruct vector %s: %s", v_id, exc)

    if not visual_vectors:
        return candidates

    # 2. Compute visual centroid and blend with query vector
    visual_centroid = np.sum(visual_vectors, axis=0) / sum(weights)
    c_norm = np.linalg.norm(visual_centroid)
    if c_norm > 0:
        visual_centroid = visual_centroid / c_norm

    # Blended PRF vector: (1 - alpha) * Text + alpha * Visual_Centroid
    blended_prf_vec = ((1.0 - blend_alpha) * q_vec) + (blend_alpha * visual_centroid)
    b_norm = np.linalg.norm(blended_prf_vec)
    if b_norm > 0:
        blended_prf_vec = blended_prf_vec / b_norm

    # 3. Rescore candidates against blended PRF vector
    updated_candidates = [dict(c) for c in candidates]

    for cand in updated_candidates:
        v_id = cand.get("vector_id")
        if v_id is None:
            continue
        try:
            cand_vec = reconstruct_fn(int(v_id))
            cv_norm = np.linalg.norm(cand_vec)
            if cv_norm > 0:
                cand_vec = cand_vec / cv_norm
                prf_sim = float(np.dot(cand_vec, blended_prf_vec))
                original_score = float(cand.get("score", cand.get("r_score", 0.0)))
                
                # Combine original score and visual PRF score
                new_score = round(float((1.0 - prf_weight) * original_score + prf_weight * max(0.0, prf_sim)), 4)
                cand["score"] = new_score
                if "r_score" in cand:
                    cand["r_score"] = new_score
                cand["prf_sim"] = round(prf_sim, 4)
        except Exception as exc:
            logger.debug("PRF rescore failed for vector %s: %s", v_id, exc)

    # 4. Re-sort candidates by new score
    updated_candidates.sort(key=lambda x: x.get("score", x.get("r_score", 0.0)), reverse=True)
    return updated_candidates
