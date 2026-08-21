"""Smart Intra-Video Scanning Algorithm.

Extracts the top candidate videos from the initial FAISS results and
expands the candidate pool by injecting every single keyframe from those videos,
scoring them accurately.
"""

from __future__ import annotations

import logging
from typing import Any
import numpy as np
from app.utils.validation import validated_kis_result
from app.core.config import settings
from app.core.exceptions import DatasetValidationError

logger = logging.getLogger(__name__)


def expand_pool_with_entire_videos(
    candidates: list[dict[str, Any]],
    query_text: str,
    kis_engine: Any,
    max_videos: int = 2,
    target_video_filter: str | None = None,
) -> list[dict[str, Any]]:
    """Identifies the top videos from candidates (or specific filtered video) and scans all their frames."""
    if not kis_engine or not kis_engine.store:
        return candidates

    top_vids = []
    if target_video_filter and target_video_filter.strip():
        filt = target_video_filter.strip().upper()
        faiss_store = getattr(kis_engine.store, "_faiss", kis_engine.store)
        all_meta = getattr(faiss_store, "metadata", [])
        matched_vids = sorted(list({str(m.get("video_id", "")) for m in all_meta if str(m.get("video_id", "")).upper().startswith(filt)}))
        top_vids = matched_vids[:max(max_videos, 5)]
    else:
        seen = set()
        for c in candidates:
            vid = str(c.get("video_id", ""))
            if vid and vid not in seen:
                seen.add(vid)
                top_vids.append(vid)
                if len(top_vids) >= max_videos:
                    break

    if not top_vids:
        return candidates

    try:
        query_vector = kis_engine.encode_query_vector(query_text).copy().reshape(-1)
        query_vector = np.asarray(query_vector, dtype=np.float32)
    except Exception as exc:
        logger.warning("smart_scan failed to encode query: %s", exc)
        return candidates

    store = kis_engine.store
    faiss_store = getattr(store, "_faiss", store)
    
    existing_vectors = {c.get("vector_id") for c in candidates if c.get("vector_id") is not None}
    new_results = []
    
    try:
        all_meta = getattr(faiss_store, "metadata", [])
        target_vids = set(top_vids)
        
        for meta in all_meta:
            vid = str(meta.get("video_id", ""))
            if vid in target_vids:
                vec_id = meta.get("vector_id")
                if vec_id is not None and vec_id not in existing_vectors:
                    try:
                        frame_vec = store.reconstruct(vec_id)
                        raw_score = float(np.dot(query_vector, frame_vec))
                        raw_cosine = max(-1.0, min(1.0, raw_score))
                        r_score = max(0.0, min(1.0, (raw_cosine + 1.0) / 2.0))
                        
                        result = {
                            "vector_id": vec_id,
                            "video_id": str(meta.get("video_id", "")),
                            "frame_id": int(meta.get("frame_id", 0)),
                            "keyframe_id": int(meta.get("keyframe_id", 0)),
                            "timestamp": float(meta.get("timestamp", 0.0)),
                            "score": r_score,
                            "r_score": r_score,
                            "raw_cosine_score": raw_cosine,
                            "sources": ["smart_scan"],
                            "source": "smart_scan",
                        }
                        new_results.append(result)
                        existing_vectors.add(vec_id)
                    except (ValueError, Exception):
                        continue
    except Exception as exc:
        logger.warning("smart_scan failed to retrieve frames: %s", exc)
        return candidates

    combined = candidates + new_results
    combined.sort(key=lambda x: x.get("score", x.get("r_score", 0.0)), reverse=True)
    
    for i, c in enumerate(combined, 1):
        c["rank"] = i
        
    logger.debug("smart_scan expanded pool by %d frames from %d videos", len(new_results), len(top_vids))
    return combined
