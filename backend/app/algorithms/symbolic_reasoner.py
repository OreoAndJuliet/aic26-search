"""0-Token Symbolic Classical Computer Vision Reasoner for VQA (AIC 2026).

Answers visual color and spatial positioning questions in < 2ms using local bounding boxes,
HSV color histogram segmentation, and centroid coordinate geometry with 0 API tokens.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

COLOR_QUESTIONS_VI = ("màu gì", "mau gi", "màu sắc", "mau sac", "màu nào", "mau nao")
COLOR_QUESTIONS_EN = ("what color", "which color", "color of", "colour of")

POSITION_QUESTIONS_VI = ("bên trái hay", "bên phải hay", "ở đâu", "vị trí nào", "nằm ở đâu", "phía nào")
POSITION_QUESTIONS_EN = ("left or right", "on the left", "on the right", "where is", "position of", "top or bottom")


def is_color_question(question: str) -> bool:
    q_low = question.lower()
    return any(p in q_low for p in COLOR_QUESTIONS_VI) or any(p in q_low for p in COLOR_QUESTIONS_EN)


def is_position_question(question: str) -> bool:
    q_low = question.lower()
    return any(p in q_low for p in POSITION_QUESTIONS_VI) or any(p in q_low for p in POSITION_QUESTIONS_EN)


def rgb_to_hsv_numpy(rgb: np.ndarray) -> np.ndarray:
    """Fast vectorized RGB to HSV conversion (H: 0-360, S: 0-1, V: 0-1)."""
    rgb_norm = rgb.astype(np.float32) / 255.0
    r, g, b = rgb_norm[..., 0], rgb_norm[..., 1], rgb_norm[..., 2]

    c_max = np.maximum(np.maximum(r, g), b)
    c_min = np.minimum(np.minimum(r, g), b)
    delta = c_max - c_min

    # Hue calculation
    h = np.zeros_like(c_max)
    mask_r = (c_max == r) & (delta > 0)
    mask_g = (c_max == g) & (delta > 0)
    mask_b = (c_max == b) & (delta > 0)

    h[mask_r] = 60.0 * (((g[mask_r] - b[mask_r]) / delta[mask_r]) % 6)
    h[mask_g] = 60.0 * (((b[mask_g] - r[mask_g]) / delta[mask_g]) + 2)
    h[mask_b] = 60.0 * (((r[mask_b] - g[mask_b]) / delta[mask_b]) + 4)

    # Saturation calculation
    s = np.zeros_like(c_max)
    mask_nz = c_max > 0
    s[mask_nz] = delta[mask_nz] / c_max[mask_nz]

    # Value calculation
    v = c_max

    return np.stack([h, s, v], axis=-1)


def classify_dominant_color_hsv(rgb_crop: np.ndarray) -> str:
    """Classify the dominant color category in an RGB image crop using HSV segmentation."""
    if rgb_crop.size == 0 or rgb_crop.shape[0] < 2 or rgb_crop.shape[1] < 2:
        return "unknown"

    hsv = rgb_to_hsv_numpy(rgb_crop)
    h = hsv[..., 0]
    s = hsv[..., 1]
    v = hsv[..., 2]

    total_pixels = h.size
    if total_pixels == 0:
        return "unknown"

    # Color bin masks
    is_black = v < 0.18
    is_white = (s < 0.15) & (v > 0.72)
    is_gray = (s < 0.22) & (v >= 0.18) & (v <= 0.72)

    # Chromatic colors
    is_chromatic = ~is_black & ~is_white & ~is_gray
    is_red = is_chromatic & ((h < 15) | (h >= 345))
    is_orange = is_chromatic & (h >= 15) & (h < 42)
    is_yellow = is_chromatic & (h >= 42) & (h < 72)
    is_green = is_chromatic & (h >= 72) & (h < 160)
    is_cyan = is_chromatic & (h >= 160) & (h < 195)
    is_blue = is_chromatic & (h >= 195) & (h < 260)
    is_purple = is_chromatic & (h >= 260) & (h < 315)
    is_pink = is_chromatic & (h >= 315) & (h < 345)

    counts = {
        "black": np.sum(is_black),
        "white": np.sum(is_white),
        "gray": np.sum(is_gray),
        "red": np.sum(is_red),
        "orange": np.sum(is_orange),
        "yellow": np.sum(is_yellow),
        "green": np.sum(is_green),
        "cyan": np.sum(is_cyan),
        "blue": np.sum(is_blue),
        "purple": np.sum(is_purple),
        "pink": np.sum(is_pink),
    }

    # Find dominant color
    dominant = max(counts.items(), key=lambda x: x[1])
    return dominant[0]


def answer_symbolic_color_vqa(
    image_path: Path,
    target_bboxes: list[list[float]],
) -> str:
    """Crop target bounding box from image and extract dominant color in < 2ms."""
    if not image_path.is_file() or not target_bboxes:
        return ""

    try:
        from PIL import Image
        with Image.open(image_path) as img:
            rgb = np.array(img.convert("RGB"))
            h, w, _ = rgb.shape

            box = target_bboxes[0]  # [ymin, xmin, ymax, xmax]
            ymin = max(0, int(box[0] * h))
            xmin = max(0, int(box[1] * w))
            ymax = min(h, int(box[2] * h))
            xmax = min(w, int(box[3] * w))

            if ymax <= ymin + 4 or xmax <= xmin + 4:
                return ""

            crop = rgb[ymin:ymax, xmin:xmax]
            return classify_dominant_color_hsv(crop)
    except Exception as exc:
        logger.debug("Symbolic color reasoning failed: %s", exc)
        return ""


def answer_symbolic_position_vqa(target_bboxes: list[list[float]]) -> str:
    """Evaluate normalized bounding box centroid to determine spatial position."""
    if not target_bboxes:
        return ""

    box = target_bboxes[0]  # [ymin, xmin, ymax, xmax]
    x_center = (box[1] + box[3]) / 2.0
    y_center = (box[0] + box[2]) / 2.0

    if x_center < 0.40:
        pos_x = "left"
    elif x_center > 0.60:
        pos_x = "right"
    else:
        pos_x = "center"

    if y_center < 0.35:
        pos_y = "top"
    elif y_center > 0.65:
        pos_y = "bottom"
    else:
        pos_y = ""

    if pos_y and pos_x != "center":
        return f"{pos_y}-{pos_x}"
    if pos_y:
        return pos_y
    return pos_x
