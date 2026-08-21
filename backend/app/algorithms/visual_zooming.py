"""Dynamic Multi-Scale Visual Zooming for Fine-Grained & Micro-Object VQA."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from PIL import Image

logger = logging.getLogger(__name__)

MICRO_OBJECTS_MAP: dict[str, list[str]] = {
    "watch": ["watch", "clock", "đồng hồ"],
    "phone": ["cell phone", "phone", "mobile", "điện thoại"],
    "cup": ["cup", "mug", "glass", "cốc", "ly"],
    "bottle": ["bottle", "chai", "bình"],
    "fruit": ["fruit", "apple", "banana", "orange", "food", "trái cây", "quả"],
    "knife": ["knife", "fork", "spoon", "dao", "thìa", "muỗng"],
    "book": ["book", "sách", "vở"],
    "bag": ["handbag", "backpack", "suitcase", "túi", "ba lô"],
    "hat": ["hat", "cap", "nón", "mũ"],
    "plate": ["plate", "bowl", "đĩa", "bát", "chén"],
    "sink": ["sink", "bồn"],
}


def detect_micro_target(question: str) -> str | None:
    """Identify if the question specifically interrogates a micro/fine-grained object."""
    q_lower = question.lower()
    for cat, terms in MICRO_OBJECTS_MAP.items():
        for t in terms:
            if re.search(r"\b" + re.escape(t) + r"\b", q_lower):
                return cat
    return None


def extract_high_res_object_crop(
    image_path: Path,
    box_norm: list[float],
    padding: float = 0.08,
) -> Path | None:
    """Crop the native high-resolution bounding box region with contextual padding."""
    if not image_path.is_file() or len(box_norm) < 4:
        return None

    try:
        with Image.open(image_path) as img:
            w, h = img.size
            ymin, xmin, ymax, xmax = box_norm[:4]

            # Add context padding
            ymin_pad = max(0.0, ymin - padding)
            xmin_pad = max(0.0, xmin - padding)
            ymax_pad = min(1.0, ymax + padding)
            xmax_pad = min(1.0, xmax + padding)

            left = int(xmin_pad * w)
            top = int(ymin_pad * h)
            right = int(xmax_pad * w)
            bottom = int(ymax_pad * h)

            if right <= left or bottom <= top:
                return None

            cropped = img.crop((left, top, right, bottom))
            out_name = f"{image_path.stem}_zoom.jpg"
            out_path = image_path.parent / out_name
            cropped.save(out_path, format="JPEG", quality=95)
            return out_path
    except Exception as exc:
        logger.warning("Failed creating high-res visual zoom crop for %s: %s", image_path, exc)
        return None
