"""Temporal Shot Consensus Graph Filtering.

Identifies temporal density clusters within candidate videos.
Boosts keyframes that have multi-frame consensus within continuous shot windows (+/- 15s)
and dampens isolated single-frame false-positive spikes.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

logger = logging.getLogger(__name__)


def apply_temporal_shot_consensus(
    candidates: list[dict[str, Any]],
    *,
    window_seconds: float = 15.0,
    consensus_boost_weight: float = 0.15,
    isolated_penalty: float = 0.04,
) -> list[dict[str, Any]]:
    """Applies temporal shot consensus re-ranking across candidate keyframes.

    Args:
        candidates: List of candidate result dictionaries.
        window_seconds: Temporal neighborhood window in seconds (default: 15.0s).
        consensus_boost_weight: Max score boost for dense multi-frame consensus clusters (default: 0.15).
        isolated_penalty: Score reduction applied to single-frame isolated spikes (default: 0.04).

    Returns:
        Updated candidate list re-sorted with temporal consensus adjustments.
    """
    if not candidates or len(candidates) <= 1 or (consensus_boost_weight <= 0.0 and isolated_penalty <= 0.0):
        return candidates

    # Group candidate indices by video_id
    video_groups: dict[str, list[int]] = defaultdict(list)
    for idx, c in enumerate(candidates):
        vid = str(c.get("video_id", ""))
        if vid:
            video_groups[vid].append(idx)

    updated = [dict(c) for c in candidates]

    for vid, indices in video_groups.items():
        # If video only has 1 hit in candidate pool, apply mild isolated penalty
        if len(indices) == 1:
            if isolated_penalty > 0.0:
                idx = indices[0]
                orig_score = float(updated[idx].get("score", updated[idx].get("r_score", 0.0)))
                new_score = round(max(0.0, orig_score - isolated_penalty), 4)
                updated[idx]["score"] = new_score
                if "r_score" in updated[idx]:
                    updated[idx]["r_score"] = new_score
                updated[idx]["temporal_consensus"] = "isolated_spike"
            continue

        # For videos with multiple hits, evaluate neighbor density within window_seconds
        timestamps = [float(updated[idx].get("timestamp", 0.0)) for idx in indices]
        scores = [float(updated[idx].get("score", updated[idx].get("r_score", 0.0))) for idx in indices]

        for i, idx in enumerate(indices):
            t_curr = timestamps[i]
            # Find neighbors within +/- window_seconds
            neighbors = [j for j, t_other in enumerate(timestamps) if i != j and abs(t_other - t_curr) <= window_seconds]

            if neighbors:
                # Calculate consensus strength
                neighbor_scores = [scores[j] for j in neighbors]
                avg_neighbor_score = sum(neighbor_scores) / len(neighbor_scores)
                density_factor = min(1.0, len(neighbors) / 3.0)  # max consensus at 3+ neighbors
                boost = consensus_boost_weight * density_factor * max(0.1, avg_neighbor_score)

                orig_score = scores[i]
                new_score = round(float(orig_score + boost), 4)
                updated[idx]["score"] = new_score
                if "r_score" in updated[idx]:
                    updated[idx]["r_score"] = new_score
                updated[idx]["temporal_consensus"] = f"cluster_{len(neighbors)+1}_frames"
                updated[idx]["consensus_boost"] = round(boost, 4)
            else:
                # Isolated frame within a video that has other frames far away
                if isolated_penalty > 0.0:
                    orig_score = scores[i]
                    new_score = round(max(0.0, orig_score - (isolated_penalty * 0.5)), 4)
                    updated[idx]["score"] = new_score
                    if "r_score" in updated[idx]:
                        updated[idx]["r_score"] = new_score

    # Re-sort candidates by updated score
    updated.sort(key=lambda x: x.get("score", x.get("r_score", 0.0)), reverse=True)
    return updated
