"""Object Class + HSV Color Co-Occurrence Reranker for KIS (AIC 2026).

Identifies (Color, Object) pairs from queries (e.g. 'green bus', 'xe buýt màu xanh', 'wooden table')
and verifies Faster R-CNN bounding box crops with local HSV color segmentation for a +0.25x precision boost.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import numpy as np

from app.algorithms.symbolic_reasoner import classify_dominant_color_hsv
from app.utils.keyframes import keyframe_image_path

logger = logging.getLogger(__name__)

# Color keyword patterns mapped to canonical HSV color bins
COLOR_KEYWORD_MAP: list[tuple[str, str]] = [
    (r"\b(màu đỏ|mau do|red)\b", "red"),
    (r"\b(màu xanh lá|xanh lá cây|màu xanh lục|green)\b", "green"),
    (r"\b(màu xanh dương|xanh da trời|màu xanh|blue)\b", "blue"),
    (r"\b(màu vàng|mau vang|yellow)\b", "yellow"),
    (r"\b(màu cam|mau cam|orange)\b", "orange"),
    (r"\b(màu trắng|mau trang|white)\b", "white"),
    (r"\b(màu đen|mau den|black)\b", "black"),
    (r"\b(màu nâu|mau nau|bằng gỗ|gỗ|brown|wooden)\b", "brown"),
    (r"\b(màu xám|mau xam|màu ghi|gray|grey)\b", "gray"),
    (r"\b(màu hồng|mau hong|pink)\b", "pink"),
    (r"\b(màu tím|mau tim|purple)\b", "purple"),
]

# Object keyword patterns mapped to Faster R-CNN class names
OBJECT_KEYWORD_MAP: list[tuple[str, str]] = [
    (r"\b(xe buýt|xe bus|bus|buses)\b", "bus"),
    (r"\b(xe hơi|xe ô tô|ô tô|car|cars|automobile)\b", "car"),
    (r"\b(xe máy|xe mô tô|motorcycle|motorbike|scooter)\b", "motorcycle"),
    (r"\b(xe đạp|bicycle|bike)\b", "bicycle"),
    (r"\b(xe tải|truck|trucks)\b", "truck"),
    (r"\b(bàn ăn|bàn gỗ|cái bàn|table|dining table)\b", "dining table"),
    (r"\b(ghế ngồi|cái ghế|chair|bench)\b", "chair"),
    (r"\b(áo|áo sơ mi|áo thun|shirt|jacket|hoodie)\b", "person"),
    (r"\b(mũ bảo hiểm|nón bảo hiểm|mũ|helmet|hat|cap)\b", "person"),
    (r"\b(balo|ba lô|túi xách|backpack|handbag|bag)\b", "backpack"),
    (r"\b(chai nước|bình nước|bottle)\b", "bottle"),
]


def extract_color_object_constraints(query: str) -> list[tuple[str, str]]:
    """Extract list of (color_name, object_class) pairs from natural language query."""
    q_low = query.lower()
    detected_pairs: list[tuple[str, str]] = []

    detected_colors: list[str] = []
    for pat, col in COLOR_KEYWORD_MAP:
        if re.search(pat, q_low):
            detected_colors.append(col)

    detected_objects: list[str] = []
    for pat, obj_cls in OBJECT_KEYWORD_MAP:
        if re.search(pat, q_low):
            detected_objects.append(obj_cls)

    # Cross pairs
    for col in detected_colors:
        for obj in detected_objects:
            detected_pairs.append((col, obj))

    return detected_pairs


def rerank_by_color_object_cooccurrence(
    candidates: list[dict[str, Any]],
    query: str,
    keyframes_dir: Path,
    objects_dir: Path,
    boost_weight: float = 0.25,
    top_k_eval: int = 15,
) -> list[dict[str, Any]]:
    """Verify color of Faster R-CNN bounding boxes and grant a precision boost to matching frames."""
    if not candidates or top_k_eval <= 0:
        return candidates

    constraints = extract_color_object_constraints(query)
    if not constraints:
        return candidates

    try:
        from PIL import Image
    except ImportError:
        return candidates

    from app.services.object_store import object_store

    updated = [dict(c) for c in candidates]
    eval_count = min(top_k_eval, len(updated))

    for i in range(eval_count):
        cand = updated[i]
        v_id = str(cand.get("video_id", ""))
        f_id = int(cand.get("keyframe_id", cand.get("frame_id", 1)))

        detections = object_store.get_detections(v_id, f_id)
        if not detections:
            continue

        img_path = keyframe_image_path(v_id, f_id, keyframes_dir=keyframes_dir)
        if not img_path.is_file():
            continue

        try:
            with Image.open(img_path) as img:
                rgb = np.array(img.convert("RGB"))
                img_h, img_w, _ = rgb.shape

                for target_color, target_obj_cls in constraints:
                    matching_dets = [
                        d for d in detections
                        if (
                            target_obj_cls in str(d.get("label", d.get("class", ""))).lower()
                            or str(d.get("label", d.get("class", ""))).lower() in target_obj_cls
                        )
                        and float(d.get("score", 0.0)) >= 0.15
                    ]

                    # If person was queried for shirt/attire
                    if not matching_dets and target_obj_cls == "person":
                        matching_dets = [
                            d for d in detections
                            if "person" in str(d.get("label", d.get("class", ""))).lower()
                        ]

                    for det in matching_dets[:3]:  # Check top 3 boxes of that class
                        box = det.get("box", [])
                        if len(box) == 4:
                            ymin = max(0, int(box[0] * img_h))
                            xmin = max(0, int(box[1] * img_w))
                            ymax = min(img_h, int(box[2] * img_h))
                            xmax = min(img_w, int(box[3] * img_w))

                            if ymax > ymin + 4 and xmax > xmin + 4:
                                crop = rgb[ymin:ymax, xmin:xmax]
                                dominant_col = classify_dominant_color_hsv(crop)

                                is_match = (
                                    dominant_col == target_color
                                    or (target_color == "brown" and dominant_col in ("brown", "orange", "yellow", "black", "gray"))
                                    or (target_color == "blue" and dominant_col in ("blue", "cyan"))
                                )

                                if is_match:
                                    base_score = float(cand.get("score", cand.get("r_score", 0.0)))
                                    cand["score"] = base_score + boost_weight
                                    cand["r_score"] = cand["score"]
                                    cand["color_object_boost"] = round(boost_weight, 3)
                                    cand["color_object_match"] = f"{target_color} {target_obj_cls}"
                                    break
        except Exception as exc:
            logger.debug("Color-object rerank failed for %s_%s: %s", v_id, f_id, exc)

    updated.sort(key=lambda x: x.get("score", x.get("r_score", 0.0)), reverse=True)
    return updated
