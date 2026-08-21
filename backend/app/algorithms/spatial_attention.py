"""Spatial Quadrant Masking and Directional Visual Attention for VQA."""

from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

SPATIAL_PATTERNS: dict[str, list[str]] = {
    "top_left": [
        r"\b(?:top-left|top left|upper-left|upper left)\b",
        r"\b(?:góc trên bên trái|phía trên bên trái|bên trái phía trên)\b",
    ],
    "top_right": [
        r"\b(?:top-right|top right|upper-right|upper right)\b",
        r"\b(?:góc trên bên phải|phía trên bên phải|bên phải phía trên)\b",
    ],
    "bottom_left": [
        r"\b(?:bottom-left|bottom left|lower-left|lower left)\b",
        r"\b(?:góc dưới bên trái|phía dưới bên trái|bên trái phía dưới)\b",
    ],
    "bottom_right": [
        r"\b(?:bottom-right|bottom right|lower-right|lower right)\b",
        r"\b(?:góc dưới bên phải|phía dưới bên phải|bên phải phía dưới)\b",
    ],
    "left": [
        r"\b(?:on the left|to the left|left side|left hand|left part|left corner|leftmost)\b",
        r"\b(?:bên trái|ở bên trái|phía bên trái|tay trái|ngoài cùng bên trái)\b",
    ],
    "right": [
        r"\b(?:on the right|to the right|right side|right hand|right part|right corner|rightmost)\b",
        r"\b(?:bên phải|ở bên phải|phía bên phải|tay phải|ngoài cùng bên phải)\b",
    ],
    "top": [
        r"\b(?:at the top|on top|top side|upper part|above)\b",
        r"\b(?:phía trên|bên trên|ở trên|phía đỉnh)\b",
    ],
    "bottom": [
        r"\b(?:at the bottom|on bottom|bottom side|lower part|below|underneath)\b",
        r"\b(?:phía dưới|bên dưới|ở dưới|phía đáy)\b",
    ],
    "center": [
        r"\b(?:in the center|in the middle|center side|middle part)\b",
        r"\b(?:ở giữa|chính giữa|trung tâm)\b",
    ],
}

QUADRANT_COORDINATES: dict[str, tuple[float, float, float, float]] = {
    # [ymin, xmin, ymax, xmax] normalized
    "left": (0.0, 0.0, 1.0, 0.60),
    "right": (0.0, 0.40, 1.0, 1.0),
    "top": (0.0, 0.0, 0.60, 1.0),
    "bottom": (0.40, 0.0, 1.0, 1.0),
    "center": (0.15, 0.15, 0.85, 0.85),
    "top_left": (0.0, 0.0, 0.60, 0.60),
    "top_right": (0.0, 0.40, 0.60, 1.0),
    "bottom_left": (0.40, 0.0, 1.0, 0.60),
    "bottom_right": (0.40, 0.40, 1.0, 1.0),
}


def parse_spatial_quadrant(question: str) -> tuple[str | None, tuple[float, float, float, float] | None]:
    """Parse spatial direction directives (left, right, top-left, center, etc.) from the question."""
    q_lower = question.lower()
    for quad_name, patterns in SPATIAL_PATTERNS.items():
        for pat in patterns:
            if re.search(pat, q_lower):
                return quad_name, QUADRANT_COORDINATES[quad_name]
    return None, None


def get_spatial_focused_image(
    image_path: Path,
    quadrant_name: str | None,
    quadrant_coords: tuple[float, float, float, float] | None,
    cache_dir: Path | None = None,
) -> Path:
    """Extract and cache a cropped visual region if spatial directive is present; otherwise returns original image."""
    if quadrant_coords is None or quadrant_name is None:
        return image_path

    if not image_path.is_file():
        return image_path

    try:
        from PIL import Image
    except ImportError:
        logger.warning("Pillow not installed; returning original image.")
        return image_path

    if cache_dir is None:
        cache_dir = Path("data/cache/spatial_crops")
    cache_dir.mkdir(parents=True, exist_ok=True)

    crop_filename = f"{image_path.parent.name}_{image_path.stem}_{quadrant_name}.jpg"
    crop_path = cache_dir / crop_filename
    if crop_path.is_file():
        return crop_path

    try:
        with Image.open(image_path) as img:
            img_rgb = img.convert("RGB")
            w, h = img_rgb.size
            ymin, xmin, ymax, xmax = quadrant_coords
            left = max(0, int(xmin * w))
            top = max(0, int(ymin * h))
            right = min(w, int(xmax * w))
            bottom = min(h, int(ymax * h))

            if right > left + 10 and bottom > top + 10:
                crop = img_rgb.crop((left, top, right, bottom))
                crop.save(crop_path, "JPEG", quality=90)
                return crop_path
    except Exception as exc:
        logger.warning("Failed creating spatial crop for %s: %s", image_path, exc)

    return image_path
