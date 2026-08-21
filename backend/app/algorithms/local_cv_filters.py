"""Local Classical Computer Vision Filters for 0-Token Posture and Color Analysis."""

from __future__ import annotations

import logging

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

COLOR_RANGES: dict[str, list[tuple[float, float]]] = {
    "red": [(0.0, 15.0), (345.0, 360.0)],
    "orange": [(15.0, 40.0)],
    "yellow": [(40.0, 75.0)],
    "green": [(80.0, 160.0)],
    "cyan": [(160.0, 190.0)],
    "blue": [(190.0, 260.0)],
    "purple": [(260.0, 315.0)],
    "pink": [(315.0, 345.0)],
}


def rgb_to_hsv_numpy(rgb_array: np.ndarray) -> np.ndarray:
    """Vectorized conversion of RGB image array (H, W, 3) to HSV (H, W, 3)."""
    rgb = rgb_array.astype(np.float32) / 255.0
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]

    maxc = np.maximum(np.maximum(r, g), b)
    minc = np.minimum(np.minimum(r, g), b)
    v = maxc
    deltac = maxc - minc

    s = np.zeros_like(maxc)
    mask = maxc != 0
    s[mask] = deltac[mask] / maxc[mask]

    h = np.zeros_like(maxc)
    mask_r = (maxc == r) & (deltac != 0)
    h[mask_r] = ((g[mask_r] - b[mask_r]) / deltac[mask_r]) % 6.0

    mask_g = (maxc == g) & (deltac != 0)
    h[mask_g] = ((b[mask_g] - r[mask_g]) / deltac[mask_g]) + 2.0

    mask_b = (maxc == b) & (deltac != 0)
    h[mask_b] = ((r[mask_b] - g[mask_b]) / deltac[mask_b]) + 4.0

    h = h * 60.0
    return np.stack([h, s, v], axis=-1)


def extract_crop_dominant_color(img_crop: Image.Image) -> tuple[str, float]:
    """Classify the dominant color of a bounding box crop using vectorized HSV histograms."""
    arr = np.asarray(img_crop.convert("RGB"))
    if arr.size == 0:
        return "unknown", 0.0

    hsv = rgb_to_hsv_numpy(arr)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    total_pixels = arr.shape[0] * arr.shape[1]

    # Neutral tones
    black_mask = v < 0.20
    white_mask = (s < 0.18) & (v > 0.70)
    gray_mask = (s < 0.18) & (v >= 0.20) & (v <= 0.70)

    color_counts: dict[str, float] = {
        "black": float(np.sum(black_mask) / total_pixels),
        "white": float(np.sum(white_mask) / total_pixels),
        "gray": float(np.sum(gray_mask) / total_pixels),
    }

    # Saturated chromatic colors
    chroma_mask = (s >= 0.22) & (v >= 0.20)
    for c_name, ranges in COLOR_RANGES.items():
        c_mask = np.zeros_like(h, dtype=bool)
        for h_min, h_max in ranges:
            c_mask |= (h >= h_min) & (h <= h_max)
        color_counts[c_name] = float(np.sum(c_mask & chroma_mask) / total_pixels)

    best_color, conf = max(color_counts.items(), key=lambda x: x[1])
    return best_color, conf


def estimate_box_posture(box_norm: list[float]) -> str:
    """Classify posture ('standing', 'sitting', 'unknown') from normalized bbox [y1, x1, y2, x2]."""
    if len(box_norm) < 4:
        return "unknown"
    y1, x1, y2, x2 = box_norm[:4]
    h = max(0.001, y2 - y1)
    w = max(0.001, x2 - x1)
    aspect_ratio = h / w

    if aspect_ratio >= 1.75:
        return "standing"
    if aspect_ratio <= 1.30:
        return "sitting"
    return "intermediate"
