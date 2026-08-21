"""Vectorized Dynamic Time Warping (DTW) & Gaussian Temporal Decay Alignment for TRAKE."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class EventCandidate:
    video_id: str
    frame_id: int
    timestamp: float
    score: float
    event_index: int
    event_text: str
    payload: dict[str, Any]


def build_event_candidates(
    *,
    event_texts: list[str],
    kis_results_per_event: list[list[dict[str, Any]]],
) -> list[list[EventCandidate]]:
    layers: list[list[EventCandidate]] = []
    for event_index, (event_text, results) in enumerate(
        zip(event_texts, kis_results_per_event, strict=True)
    ):
        layer: list[EventCandidate] = []
        for result in results:
            layer.append(
                EventCandidate(
                    video_id=str(result.get("video_id", "")),
                    frame_id=int(result.get("frame_id", result.get("keyframe_id", 0))),
                    timestamp=float(result.get("timestamp", 0.0)),
                    score=float(result.get("score", result.get("r_score", 0.0))),
                    event_index=event_index,
                    event_text=event_text,
                    payload=result,
                )
            )
        layers.append(layer)
    return layers


def _dtw_vectorized_video_path(
    per_video_layers: list[list[EventCandidate]],
    target_gap_seconds: float = 15.0,
    gap_sigma_seconds: float = 25.0,
    max_gap_seconds: float = 300.0,
    w_event: float = 0.70,
    w_temporal: float = 0.30,
) -> tuple[list[EventCandidate], float]:
    """Vectorized Dynamic Time Warping path finding with Gaussian temporal spacing kernel."""
    num_layers = len(per_video_layers)
    if num_layers == 0 or any(not layer for layer in per_video_layers):
        return [], float("-inf")

    timestamps = [
        np.array([c.timestamp for c in layer], dtype=np.float32)
        for layer in per_video_layers
    ]
    frame_ids = [
        np.array([c.frame_id for c in layer], dtype=np.int32)
        for layer in per_video_layers
    ]
    scores = [
        np.array([c.score for c in layer], dtype=np.float32)
        for layer in per_video_layers
    ]

    accum_scores = scores[0].copy()
    backpointers: list[np.ndarray] = []

    for l in range(1, num_layers):
        t_prev = timestamps[l - 1]
        f_prev = frame_ids[l - 1]
        t_curr = timestamps[l]
        f_curr = frame_ids[l]
        s_curr = scores[l]

        # Pairwise temporal gap matrix (M, N)
        delta_t = t_curr[None, :] - t_prev[:, None]
        delta_f = f_curr[None, :] - f_prev[:, None]

        # Valid forward-in-time mask: t_curr > t_prev (or if equal, f_curr > f_prev) and <= max_gap
        valid_mask = ((delta_t > 0) | ((delta_t == 0) & (delta_f > 0))) & (delta_t <= max_gap_seconds)

        # Gaussian temporal kernel scoring realistic event progression
        gaussian_kernel = np.exp(-((delta_t - target_gap_seconds) ** 2) / (2.0 * (gap_sigma_seconds ** 2)))

        # Transition matrix
        trans_matrix = accum_scores[:, None] + (w_event * s_curr[None, :]) + (w_temporal * gaussian_kernel)
        trans_matrix[~valid_mask] = -1e9

        best_prev = np.argmax(trans_matrix, axis=0)
        best_vals = np.max(trans_matrix, axis=0)

        has_valid = np.any(valid_mask, axis=0)
        best_vals[~has_valid] = -1e9

        backpointers.append(best_prev)
        accum_scores = best_vals

    best_final_idx = int(np.argmax(accum_scores))
    if accum_scores[best_final_idx] <= -1e8:
        return [], float("-inf")

    # Reconstruct optimal DTW path
    path_indices = [best_final_idx]
    for l in range(num_layers - 2, -1, -1):
        prev_idx = int(backpointers[l][path_indices[-1]])
        path_indices.append(prev_idx)
    path_indices.reverse()

    path = [per_video_layers[l][path_indices[l]] for l in range(num_layers)]
    final_score = float(accum_scores[best_final_idx])
    return path, final_score


def align_events_dtw(
    event_layers: list[list[EventCandidate]],
    max_gap_seconds: float = 300.0,
    target_gap_seconds: float = 15.0,
    gap_sigma_seconds: float = 25.0,
    w_event: float = 0.85,
    w_temporal: float = 0.15,
) -> tuple[list[EventCandidate], float] | None:
    """Pick optimal increasing-time trajectory for event candidates across videos using vectorized DTW."""
    if not event_layers or any(not layer for layer in event_layers):
        return None

    video_ids = {candidate.video_id for layer in event_layers for candidate in layer}
    best_path: list[EventCandidate] | None = None
    best_score = float("-inf")

    for video_id in video_ids:
        per_video_layers: list[list[EventCandidate]] = []
        for layer in event_layers:
            filtered = [c for c in layer if c.video_id == video_id]
            if not filtered:
                per_video_layers = []
                break
            per_video_layers.append(filtered)

        if not per_video_layers:
            continue

        path, score = _dtw_vectorized_video_path(
            per_video_layers,
            target_gap_seconds=target_gap_seconds,
            gap_sigma_seconds=gap_sigma_seconds,
            max_gap_seconds=max_gap_seconds,
            w_event=w_event,
            w_temporal=w_temporal,
        )
        if path and score > best_score:
            best_score = score
            best_path = path

    if best_path is None:
        return None

    return best_path, best_score


def align_topk_events_dtw(
    event_layers: list[list[EventCandidate]],
    top_k: int = 5,
    max_gap_seconds: float = 300.0,
    target_gap_seconds: float = 15.0,
    gap_sigma_seconds: float = 25.0,
    w_event: float = 0.70,
    w_temporal: float = 0.30,
) -> list[tuple[list[EventCandidate], float]]:
    """Return Top-K ranked video trajectories using vectorized DTW."""
    if not event_layers or any(not layer for layer in event_layers):
        return []

    video_ids = {candidate.video_id for layer in event_layers for candidate in layer}
    candidate_paths: list[tuple[list[EventCandidate], float]] = []

    for video_id in video_ids:
        per_video_layers: list[list[EventCandidate]] = []
        for layer in event_layers:
            filtered = [c for c in layer if c.video_id == video_id]
            if not filtered:
                per_video_layers = []
                break
            per_video_layers.append(filtered)

        if not per_video_layers:
            continue

        path, score = _dtw_vectorized_video_path(
            per_video_layers,
            target_gap_seconds=target_gap_seconds,
            gap_sigma_seconds=gap_sigma_seconds,
            max_gap_seconds=max_gap_seconds,
            w_event=w_event,
            w_temporal=w_temporal,
        )
        if path and score > float("-inf"):
            candidate_paths.append((path, score))

    candidate_paths.sort(key=lambda x: x[1], reverse=True)
    return candidate_paths[:top_k]
