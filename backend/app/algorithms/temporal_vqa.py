"""Multi-Frame Temporal Context and Dynamic Action Storyboard Builder for VQA."""

from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

DYNAMIC_ACTION_PATTERNS: list[str] = [
    r"\b(?:enter|entering|enters|entered|walks in|walking in)\b",
    r"\b(?:leave|leaving|leaves|left|walks out|walking out|exiting|exits)\b",
    r"\b(?:open|opening|opens|opened|close|closing|closes|closed)\b",
    r"\b(?:sit down|sitting down|sits down|sat down|stand up|standing up|stands up|stood up)\b",
    r"\b(?:pick up|picking up|picks up|put down|putting down|puts down)\b",
    r"\b(?:start|starting|starts|stop|stopping|stops|stopped)\b",
    r"\b(?:turn on|turning on|turns on|turn off|turning off|turns off)\b",
    r"\b(?:đi vào|bước vào|ra ngoài|đi ra|bước ra)\b",
    r"\b(?:mở|đóng|ngồi xuống|đứng dậy|đứng lên|cầm lên|đặt xuống)\b",
]


def is_dynamic_action_question(question: str) -> bool:
    """Detect if question requires temporal progression to verify an action or state change."""
    q_lower = question.lower()
    for pat in DYNAMIC_ACTION_PATTERNS:
        if re.search(pat, q_lower):
            return True
    return False


def build_temporal_storyboard(
    video_id: str,
    keyframe_id: int,
    keyframes_dir: Path,
    cache_dir: Path | None = None,
) -> Path | None:
    """Assemble a 3-frame horizontal temporal storyboard [t-1, t0, t+1] for action comprehension."""
    if cache_dir is None:
        cache_dir = Path("data/cache/temporal_storyboards")
    cache_dir.mkdir(parents=True, exist_ok=True)

    out_path = cache_dir / f"{video_id}_{keyframe_id}_storyboard.jpg"
    if out_path.is_file():
        return out_path

    v_dir = keyframes_dir / video_id
    if not v_dir.is_dir():
        return None

    try:
        from PIL import Image, ImageDraw
    except ImportError:
        logger.warning("Pillow not installed; skipping storyboard construction.")
        return None

    candidates = [
        max(1, keyframe_id - 1),
        keyframe_id,
        keyframe_id + 1,
    ]

    images: list[Image.Image] = []
    for k in candidates:
        img_p = v_dir / f"{k:03d}.jpg"
        if not img_p.is_file():
            img_p = v_dir / f"{k}.jpg"
        if img_p.is_file():
            try:
                with Image.open(img_p) as _im:
                    images.append(_im.convert("RGB"))
            except Exception:
                pass

    if len(images) < 2:
        return None

    try:
        target_h = 360
        resized: list[Image.Image] = []
        for img in images:
            w, h = img.size
            new_w = int(w * (target_h / h))
            resized.append(img.resize((new_w, target_h), Image.Resampling.BILINEAR))

        total_w = sum(img.size[0] for img in resized)
        storyboard = Image.new("RGB", (total_w, target_h + 30), (20, 20, 20))

        labels = (
            ["[t-1] Before", "[t0] Target Event", "[t+1] After"]
            if len(resized) == 3
            else ["[t0] Target Event", "[t+1] After"]
        )
        x_offset = 0
        draw = ImageDraw.Draw(storyboard)
        for i, img in enumerate(resized):
            storyboard.paste(img, (x_offset, 0))
            lbl = labels[i] if i < len(labels) else ""
            draw.text((x_offset + 10, target_h + 5), lbl, fill=(255, 255, 255))
            x_offset += img.size[0]

        storyboard.save(out_path, "JPEG", quality=88)
        return out_path
    except Exception as exc:
        logger.warning("Failed building temporal storyboard for %s/%s: %s", video_id, keyframe_id, exc)
        return None
