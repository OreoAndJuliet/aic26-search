"""Reciprocal Rank Fusion (RRF) Engine for Multi-Modal Search (AIC 2026).

Implements Cormack RRF (SIGIR) to merge visual CLIP keyframe candidates
with BM25 MediaInfo metadata candidates and OCR matches:

    Score_RRF(d) = sum_m [ w_m / (k + rank_m(d)) ]
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def apply_reciprocal_rank_fusion(
    visual_candidates: list[dict[str, Any]],
    mediainfo_video_ranks: list[tuple[str, float]],
    ocr_video_ranks: list[tuple[str, float]] | None = None,
    k_constant: int = 60,
    w_visual: float = 0.70,
    w_media: float = 0.20,
    w_ocr: float = 0.10,
) -> list[dict[str, Any]]:
    """Fuse visual keyframe rankings with MediaInfo and OCR video-level rankings.

    Args:
        visual_candidates: List of candidate dictionaries from FAISS retrieval.
        mediainfo_video_ranks: Ranked list of (video_id, bm25_score) from MediaInfoStore.
        ocr_video_ranks: Optional ranked list of (video_id, ocr_score) from OCRStore.
        k_constant: Standard RRF damping parameter (default 60).
        w_visual: Weight for visual CLIP rank.
        w_media: Weight for MediaInfo BM25 rank.
        w_ocr: Weight for OCR text rank.

    Returns:
        Reranked list of candidate dictionaries with rrf_score and updated rank.
    """
    if not visual_candidates:
        return visual_candidates

    # Map MediaInfo video ranks (1-indexed)
    media_rank_map: dict[str, int] = {}
    for rank, (v_id, _) in enumerate(mediainfo_video_ranks, start=1):
        media_rank_map[v_id] = rank

    # Map OCR video ranks (1-indexed)
    ocr_rank_map: dict[str, int] = {}
    if ocr_video_ranks:
        for rank, (v_id, _) in enumerate(ocr_video_ranks, start=1):
            ocr_rank_map[v_id] = rank

    fused_results = [dict(c) for c in visual_candidates]

    for visual_rank, item in enumerate(fused_results, start=1):
        v_id = str(item.get("video_id", ""))

        # Visual RRF component
        rrf_visual = w_visual / float(k_constant + visual_rank)

        # MediaInfo RRF component
        if v_id in media_rank_map:
            m_rank = media_rank_map[v_id]
            rrf_media = w_media / float(k_constant + m_rank)
            item["mediainfo_match"] = True
            item["mediainfo_rank"] = m_rank
        else:
            rrf_media = 0.0

        # OCR RRF component
        if v_id in ocr_rank_map:
            o_rank = ocr_rank_map[v_id]
            rrf_ocr = w_ocr / float(k_constant + o_rank)
            item["ocr_match"] = True
            item["ocr_rank"] = o_rank
        else:
            rrf_ocr = 0.0

        total_rrf = rrf_visual + rrf_media + rrf_ocr
        item["rrf_score"] = round(total_rrf, 6)

        # Blend RRF score with existing cosine score to preserve intra-video keyframe distinction
        base_s = float(item.get("score", item.get("r_score", 0.0)))
        # Normalize RRF to similar scale [0..1]
        scaled_rrf = total_rrf * float(k_constant)
        item["score"] = round(0.60 * base_s + 0.40 * scaled_rrf, 6)
        item["r_score"] = item["score"]

    # Re-sort descending by fused score
    fused_results.sort(key=lambda x: x.get("score", 0.0), reverse=True)

    # Update ranks
    for r, item in enumerate(fused_results, start=1):
        item["rank"] = r

    return fused_results
