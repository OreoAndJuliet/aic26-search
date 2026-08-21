"""Intra-video diversification and temporal deduplication for search results.

Prevents nearly identical sub-second keyframes from the same video shot
from monopolizing the Top-K ranking list.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.core.config import settings


def apply_intra_video_diversification(
    results: list[dict[str, Any]],
    *,
    min_gap_seconds: float | None = None,
    max_per_video: int | None = None,
    penalty_weight: float | None = None,
    mode: str | None = None,
) -> list[dict[str, Any]]:
    """Diversify Top-K results by suppressing redundant keyframes from the same video shot.

    Args:
        results: Candidate list sorted by score descending.
        min_gap_seconds: Minimum temporal separation between keyframes of the same video.
        max_per_video: Maximum keyframe entries allowed for a single video.
        penalty_weight: Soft penalty factor for near-duplicate frames (0.0 to 1.0).
        mode: 'soft_penalty' (reduces duplicate score) or 'peak_filter' (drops duplicate).

    Returns:
        Diversified candidate list.
    """
    if not results or not settings.DIVERSIFICATION_ENABLED:
        return results

    gap_sec = min_gap_seconds if min_gap_seconds is not None else settings.DIVERSIFICATION_MIN_GAP_SECONDS
    max_vid = max_per_video if max_per_video is not None else settings.DIVERSIFICATION_MAX_PER_VIDEO
    pen_weight = penalty_weight if penalty_weight is not None else settings.DIVERSIFICATION_PENALTY_WEIGHT
    div_mode = (mode or settings.DIVERSIFICATION_MODE).lower().strip()

    if gap_sec <= 0.0 and max_vid <= 0:
        return results

    if div_mode == "peak_filter":
        # Hard filtering: Keep only non-overlapping peak moments up to max_per_video
        diversified: list[dict[str, Any]] = []
        video_timestamps: dict[str, list[float]] = defaultdict(list)

        for candidate in results:
            vid = str(candidate.get("video_id", ""))
            ts = float(candidate.get("timestamp", 0.0))

            # Check if this video has reached max_per_video
            if max_vid > 0 and len(video_timestamps[vid]) >= max_vid:
                continue

            # Check if within min_gap_seconds of any already-selected frame in same video
            is_redundant = any(abs(ts - prev_ts) < gap_sec for prev_ts in video_timestamps[vid])
            if is_redundant:
                continue

            video_timestamps[vid].append(ts)
            diversified.append(dict(candidate))

        for rank, item in enumerate(diversified, start=1):
            item["rank"] = rank

        return diversified

    else:
        # Soft penalty mode (default): Scale down redundant frames rather than discarding them entirely
        diversified_results = [dict(c) for c in results]
        # Keep track of selected top keyframes per video with their timestamps and scores
        seen_peaks: dict[str, list[tuple[float, float]]] = defaultdict(list)

        for item in diversified_results:
            vid = str(item.get("video_id", ""))
            ts = float(item.get("timestamp", 0.0))
            score = float(item.get("score", item.get("r_score", 0.0)))

            peaks = seen_peaks[vid]
            total_penalty = 0.0

            # 1. Temporal gap penalty relative to nearest earlier (higher-ranked) peak
            # Only penalize near-duplicates within the same temporal shot (dt < gap_sec)
            for peak_ts, peak_score in peaks:
                dt = abs(ts - peak_ts)
                if dt < gap_sec:
                    # Gaussian proximity decay penalty for near-identical frames
                    overlap_ratio = 1.0 - (dt / gap_sec)
                    penalty = pen_weight * overlap_ratio * peak_score
                    total_penalty = max(total_penalty, penalty)

            # 2. Shot-cluster saturation penalty:
            # Only penalize if there are already max_vid frames in the SAME local time window (within 45s)
            # Do NOT penalize frames from completely different scenes/shots (e.g. 102s vs 737s)
            if max_vid > 0:
                local_shot_frames = [p_ts for p_ts, _ in peaks if abs(ts - p_ts) <= 45.0]
                if len(local_shot_frames) >= max_vid:
                    total_penalty = max(total_penalty, 0.08)

            if total_penalty > 0.0:
                new_score = round(max(0.0, score - total_penalty), 6)
                item["diversity_penalty"] = round(total_penalty, 6)
                item["score"] = new_score
                item["r_score"] = new_score

            peaks.append((ts, score))

        # Re-sort by updated scores
        diversified_results.sort(
            key=lambda row: (
                -float(row.get("score", row.get("r_score", 0.0))),
                int(row.get("rank", 999)),
            )
        )

        for rank, item in enumerate(diversified_results, start=1):
            item["rank"] = rank

        return diversified_results
