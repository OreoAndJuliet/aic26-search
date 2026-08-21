"""Crop-Level Regional CLIP Alignment for fine-grained attribute & color re-ranking."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


def apply_crop_clip_alignment(
    candidates: list[dict[str, Any]],
    query_vector: np.ndarray,
    text_encoder: Any,
    *,
    keyframes_dir: Path,
    objects_dir: Path,
    weight: float = 0.12,
    top_k_eval: int = 5,
    max_crops_per_frame: int = 3,
    min_box_score: float = 0.15,
    min_box_area: float = 0.002,
) -> list[dict[str, Any]]:
    """Re-ranks top candidate keyframes by evaluating regional bounding box crop embeddings against the query vector."""
    if not candidates or weight <= 0.0 or top_k_eval <= 0:
        return candidates

    if not hasattr(text_encoder, "_model"):
        return candidates

    try:
        from PIL import Image
    except ImportError:
        logger.warning("Pillow not installed; skipping crop-level CLIP alignment.")
        return candidates

    model = getattr(text_encoder, "_model", None)
    if model is None:
        return candidates

    # Ensure query vector is a 1D unit vector
    q_vec = np.asarray(query_vector).flatten().astype(np.float32)
    norm = np.linalg.norm(q_vec)
    if norm > 0:
        q_vec = q_vec / norm

    from app.services.object_store import object_store
    from app.utils.keyframes import keyframe_image_path

    updated_candidates = [dict(c) for c in candidates]
    eval_count = min(top_k_eval, len(updated_candidates))

    for i in range(eval_count):
        candidate = updated_candidates[i]
        video_id = candidate.get("video_id", "")
        keyframe_id = int(candidate.get("keyframe_id", candidate.get("frame_id", 1)))

        detections = object_store.get_detections(video_id, keyframe_id)
        if not detections:
            continue

        # Filter valid bounding boxes
        valid_boxes = []
        for det in detections:
            score = float(det.get("score", 0.0))
            box = det.get("box", [0, 0, 0, 0])
            area = max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])
            if score >= min_box_score and area >= min_box_area:
                valid_boxes.append((score, area, box))

        if not valid_boxes:
            continue

        # Sort by area * score to pick the most prominent objects
        valid_boxes.sort(key=lambda x: x[0] * np.sqrt(x[1]), reverse=True)
        selected_boxes = valid_boxes[:max_crops_per_frame]

        # Load image and extract crops
        img_path = keyframe_image_path(video_id, keyframe_id, keyframes_dir=keyframes_dir)
        if not img_path.is_file():
            continue

        try:
            with Image.open(img_path) as img:
                img_rgb = img.convert("RGB")
                w, h = img_rgb.size
                crops = []
                for _, _, (ymin, xmin, ymax, xmax) in selected_boxes:
                    left = max(0, int(xmin * w))
                    top = max(0, int(ymin * h))
                    right = min(w, int(xmax * w))
                    bottom = min(h, int(ymax * h))
                    if right > left + 4 and bottom > top + 4:
                        crops.append(img_rgb.crop((left, top, right, bottom)))

                if not crops:
                    continue

                # Batch encode crops
                crop_embs = model.encode(
                    crops,
                    show_progress_bar=False,
                    normalize_embeddings=True,
                    convert_to_numpy=True,
                ).astype(np.float32)

                sims = np.dot(crop_embs, q_vec)
                max_crop_sim = float(np.max(sims))

                # If crop has positive regional alignment (>0.18), apply boost
                if max_crop_sim > 0.18:
                    boost = weight * max(0.0, max_crop_sim - 0.18)
                    original_score = candidate.get("score", candidate.get("r_score", 0.0))
                    new_score = round(float(original_score + boost), 4)
                    candidate["score"] = new_score
                    if "r_score" in candidate:
                        candidate["r_score"] = new_score
                    candidate["crop_alignment_boost"] = round(boost, 4)
                    candidate["crop_alignment_max_sim"] = round(max_crop_sim, 4)
        except Exception as exc:
            logger.debug("Crop extraction failed for %s/%s: %s", video_id, keyframe_id, exc)

    # Re-sort candidates by boosted score
    updated_candidates.sort(key=lambda x: x.get("score", x.get("r_score", 0.0)), reverse=True)
    return updated_candidates
