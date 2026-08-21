import logging
import math
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.exceptions import DatasetValidationError
from app.utils.keyframes import keyframe_thumbnail_url

logger = logging.getLogger(__name__)


def validated_kis_result(
    metadata: dict[str, Any],
    raw_score: float,
    *,
    static_dir: Path,
    backend_host: str,
    vector_id: int | None = None,
) -> dict[str, Any]:
    """Validate a mapped FAISS hit before exposing it in an API response."""
    try:
        video_id = str(metadata["video_id"]).strip()
        frame_id = int(metadata["frame_id"])
        keyframe_id = int(metadata["keyframe_id"])
        timestamp = float(metadata["timestamp"])
        image_path_raw = str(metadata["image_path"])
    except (KeyError, TypeError, ValueError) as exc:
        raise DatasetValidationError("Retrieved metadata is malformed.") from exc

    if not video_id or frame_id < 0 or keyframe_id < 0 or not math.isfinite(timestamp):
        raise DatasetValidationError("Retrieved metadata contains invalid values.")
    if not math.isfinite(raw_score):
        raise DatasetValidationError("FAISS returned an invalid similarity score.")

    # Resolve image_path: support both relative paths (portable) and absolute paths (legacy).
    image_path = Path(image_path_raw)
    if image_path.is_absolute():
        # Legacy absolute path from old build_index.py — reconstruct from components
        # to make it portable.
        if len(image_path.parts) >= 3:
            resolved_image_path = static_dir.resolve() / image_path.parts[-3] / image_path.parts[-2] / image_path.parts[-1]
        elif len(image_path.parts) >= 2:
            resolved_image_path = static_dir.resolve() / "keyframes" / image_path.parts[-2] / image_path.parts[-1]
        else:
            resolved_image_path = (static_dir / "keyframes" / video_id / f"{keyframe_id:03d}.jpg").resolve()
    else:
        # Relative path (new portable format) — join with static_dir
        resolved_image_path = (static_dir / image_path).resolve()

    # Security: prevent path traversal attacks (e.g., ../../etc/passwd)
    static_root = static_dir.resolve()
    try:
        resolved_image_path.relative_to(static_root)
    except ValueError:
        # Try resolving relative to keyframes dir as well for flexibility
        keyframes_root = (static_dir / "keyframes").resolve()
        try:
            resolved_image_path = (keyframes_root / video_id / f"{keyframe_id:03d}.jpg").resolve()
            resolved_image_path.relative_to(static_root)
        except ValueError as exc:
            raise DatasetValidationError("Retrieved image path is outside the static directory.") from exc

    # File existence check - controlled by STRICT_IMAGE_VALIDATION
    if settings.STRICT_IMAGE_VALIDATION and not resolved_image_path.is_file():
        raise DatasetValidationError("Retrieved image file is missing.")
    elif not settings.STRICT_IMAGE_VALIDATION and False: # we just skip it
        pass

    raw_cosine = max(-1.0, min(1.0, raw_score))
    r_score = max(0.0, min(1.0, (raw_cosine + 1.0) / 2.0))

    return {
        "vector_id": vector_id,
        "video_id": video_id,
        "frame_id": frame_id,
        "keyframe_id": keyframe_id,
        "timestamp": timestamp,
        "thumbnail_url": keyframe_thumbnail_url(video_id, frame_id, backend_host=backend_host),
        "image_url": keyframe_thumbnail_url(video_id, frame_id, backend_host=backend_host),
        "answer": None,
        "score": r_score,
        "r_score": r_score,
        "raw_cosine_score": raw_cosine,
    }
