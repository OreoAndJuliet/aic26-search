"""TRAKE engine: multi-event KIS retrieval with temporal alignment."""

from __future__ import annotations

import logging
from typing import Any

from app.algorithms.temporal_alignment import (
    align_events_dtw,
    align_topk_events_dtw,
    build_event_candidates,
)
from app.core.config import settings
from app.core.exceptions import RetrievalUnavailableError
from app.services.kis_engine import kis_engine

logger = logging.getLogger(__name__)


class TRAKEEngine:
    def align_events(
        self,
        english_events: list[str],
        *,
        original_events: list[str] | None = None,
        top_k_per_event: int = 100,
        max_gap_seconds: float | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        if not english_events:
            return [], {
                "video_id": None,
                "event_frames": [],
                "event_count": 0,
                "alignment_score": 0.0,
                "dtw_score": 0.0,
            }

        original_events = original_events or english_events

        # Use config default if not specified
        if max_gap_seconds is None:
            max_gap_seconds = settings.TRAKE_MAX_GAP_SECONDS

        # Try initial top_k_per_event, then fallback to higher values if alignment fails
        # Internal search allows deeper retrieval than the external 100 schema limit
        max_allowed = max(top_k_per_event * 4, 1000)
        fallback_top_k_values = [top_k_per_event, min(top_k_per_event * 3, 300), max_allowed]
        last_error = None
        
        for attempt_top_k in fallback_top_k_values:
            logger.info(f"TRAKE: Attempting alignment with top_k_per_event={attempt_top_k}, max_gap={max_gap_seconds}s")
            
            try:
                kis_results_per_event = []
                from app.features.search.retrieval import run_kis_retrieval
                for en_evt, raw_evt in zip(english_events, original_events):
                    results_per_evt, _metrics = run_kis_retrieval(en_evt, attempt_top_k, raw_query=raw_evt)
                    kis_results_per_event.append(results_per_evt)

                # Edge case: if any event returns no results, skip this attempt
                if any(not results for results in kis_results_per_event):
                    try:
                        idx = next(i for i, r in enumerate(kis_results_per_event) if not r)
                    except StopIteration:
                        idx = 0
                    last_error = f"Event {idx} returned no results"
                    logger.warning("TRAKE: %s", last_error)
                    continue
                
                event_layers = build_event_candidates(
                    event_texts=english_events,
                    kis_results_per_event=kis_results_per_event,
                )
                alignment = align_events_dtw(
                    event_layers,
                    max_gap_seconds=max_gap_seconds,
                    target_gap_seconds=settings.TRAKE_TARGET_GAP_SECONDS,
                    gap_sigma_seconds=settings.TRAKE_GAP_SIGMA_SECONDS,
                )
                
                if alignment is not None:
                    path, dtw_score = alignment
                    event_count = len(path)
                    alignment_score = dtw_score / event_count if event_count else 0.0

                    # Calculate temporal gaps for metadata
                    temporal_gaps = []
                    for i in range(1, len(path)):
                        gap = path[i].timestamp - path[i-1].timestamp
                        temporal_gaps.append(round(gap, 2))

                    results: list[dict[str, Any]] = []
                    for rank, candidate in enumerate(path, start=1):
                        item = dict(candidate.payload)
                        item.update(
                            {
                                "rank": rank,
                                "event_index": candidate.event_index,
                                "event_text": candidate.event_text,
                                "answer": None,
                            }
                        )
                        results.append(item)

                    # Extract top-k candidate trajectories for full submission ranking
                    top_paths = align_topk_events_dtw(
                        event_layers,
                        top_k=100,
                        max_gap_seconds=max_gap_seconds,
                        target_gap_seconds=settings.TRAKE_TARGET_GAP_SECONDS,
                        gap_sigma_seconds=settings.TRAKE_GAP_SIGMA_SECONDS,
                    )
                    candidate_trajectories = [
                        [p[0].video_id, *[c.frame_id for c in p]]
                        for p, _ in top_paths
                        if p
                    ]

                    trake_meta = {
                        "video_id": path[0].video_id,
                        "event_frames": [candidate.frame_id for candidate in path],
                        "candidate_trajectories": candidate_trajectories,
                        "event_count": event_count,
                        "alignment_score": round(alignment_score, 6),
                        "dtw_score": round(dtw_score, 6),
                        "top_k_used": attempt_top_k,
                        "temporal_gaps": temporal_gaps,
                        "max_gap_seconds": max_gap_seconds,
                    }
                    logger.info(f"TRAKE: Successfully aligned with top_k_per_event={attempt_top_k}, temporal_gaps={temporal_gaps}")
                    return results, trake_meta
                else:
                    last_error = f"No alignment found with top_k_per_event={attempt_top_k}"
                    logger.warning(f"TRAKE: {last_error}")
                    
            except (RetrievalUnavailableError, RuntimeError, ValueError, OSError) as exc:
                last_error = f"Alignment attempt failed: {exc}"
                logger.error("TRAKE: %s", last_error)
                continue
        
        # All attempts failed - return with helpful error information
        return [], {
            "video_id": None,
            "event_frames": [],
            "event_count": len(english_events),
            "alignment_score": 0.0,
            "dtw_score": 0.0,
            "error": last_error,
            "suggestion": "Try increasing top_k_per_event, adjust max_gap_seconds, or check if events can occur in sequence",
        }

    def align(self, english_text: str, top_k: int = 100) -> list[dict[str, Any]]:
        """Backward-compatible single-string entrypoint."""
        results, _meta = self.align_events([english_text], top_k_per_event=top_k)
        return results


trake_engine = TRAKEEngine()
