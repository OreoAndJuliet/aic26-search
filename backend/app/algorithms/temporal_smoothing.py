"""Temporal keyframe smoothing for KIS search results.

Aggregates mutual score reinforcement across temporally adjacent keyframes
within the same video using Gaussian-weighted neighbor decay.
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

from app.core.config import settings


def apply_temporal_smoothing(
    results: list[dict[str, Any]],
    *,
    window_seconds: float | None = None,
    sigma: float | None = None,
    weight: float | None = None,
) -> list[dict[str, Any]]:
    """Apply Gaussian-weighted temporal score smoothing across neighboring frames in the same video.

    Args:
        results: List of candidate dictionaries with video_id, timestamp, score / r_score.
        window_seconds: Max temporal distance in seconds to consider as neighbors.
        sigma: Standard deviation for Gaussian decay (decay speed).
        weight: Importance weight for the aggregated neighbor contribution.

    Returns:
        Reranked list of candidates with updated score/r_score and temporal_boost field.
    """
    if not results:
        return results

    # If parameters not explicitly provided and feature disabled, return as-is
    if weight is None and not settings.TEMPORAL_SMOOTHING_ENABLED:
        for c in results:
            c.setdefault("temporal_boost", 0.0)
        return results

    w_sec = window_seconds if window_seconds is not None else settings.TEMPORAL_SMOOTHING_WINDOW_SECONDS
    sig = sigma if sigma is not None else settings.TEMPORAL_SMOOTHING_SIGMA
    w_weight = weight if weight is not None else settings.TEMPORAL_SMOOTHING_WEIGHT

    if w_weight <= 0.0 or w_sec <= 0.0 or sig <= 0.0:
        for c in results:
            c.setdefault("temporal_boost", 0.0)
        return results

    # Group candidates by video_id
    video_groups: dict[str, list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    for idx, candidate in enumerate(results):
        video_id = str(candidate.get("video_id", ""))
        if video_id:
            video_groups[video_id].append((idx, candidate))

    smoothed_results = [dict(c) for c in results]
    two_sig_sq = 2.0 * (sig ** 2)

    for video_id, entries in video_groups.items():
        if len(entries) <= 1:
            # Single frame from this video, no neighbors to smooth with
            continue

        for i, (orig_idx_i, cand_i) in enumerate(entries):
            t_i = float(cand_i.get("timestamp", 0.0))
            s_i = float(cand_i.get("score", cand_i.get("r_score", cand_i.get("raw_score", 0.0))))

            neighbor_boost = 0.0
            neighbor_count = 0

            max_neighbor_s = 0.0
            for j, (orig_idx_j, cand_j) in enumerate(entries):
                if i == j:
                    continue
                t_j = float(cand_j.get("timestamp", 0.0))
                dt = abs(t_i - t_j)

                if dt <= w_sec:
                    s_j = float(cand_j.get("score", cand_j.get("r_score", cand_j.get("raw_score", 0.0))))
                    gaussian_weight = math.exp(-(dt ** 2) / two_sig_sq)
                    neighbor_boost += gaussian_weight * s_j
                    neighbor_count += 1
                    max_neighbor_s = max(max_neighbor_s, s_j)

            if neighbor_count > 0:
                # Shot-level Gaussian smoothed neighbor consensus
                avg_contrib = neighbor_boost / neighbor_count
                combined_shot_contrib = (0.60 * avg_contrib) + (0.40 * max_neighbor_s)
                # Convex blend: (1 - w) * original_score + w * neighbor_consensus
                blend_factor = min(1.0, w_weight * (min(neighbor_count, 3) / 3.0))
                new_score = round(((1.0 - blend_factor) * s_i) + (blend_factor * combined_shot_contrib), 6)
                # Only allow upward nudges — never penalize already-high confidence frames
                new_score = max(s_i, new_score)
                temporal_boost = round(new_score - s_i, 6)
            else:
                temporal_boost = 0.0
                new_score = s_i

            smoothed_results[orig_idx_i]["temporal_boost"] = temporal_boost
            smoothed_results[orig_idx_i]["score"] = new_score
            smoothed_results[orig_idx_i]["r_score"] = new_score

    # Re-sort by final score descending
    smoothed_results.sort(
        key=lambda row: (
            -float(row.get("score", row.get("r_score", 0.0))),
            int(row.get("rank", 999)),
        )
    )

    # Re-assign ranks 1..N
    for rank, item in enumerate(smoothed_results, start=1):
        item["rank"] = rank

    return smoothed_results
