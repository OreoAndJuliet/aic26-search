"""Frontend static URL helpers for keyframe thumbnails."""

from pathlib import Path


def keyframe_thumbnail_path(video_id: str, frame_id: int) -> str:
    """Relative thumbnail URL using original frame_id per FE contract.
    
    Updated to match specification: http://<backend_ip>/keyframes/<video_name>/<frame_id>.jpg
    """
    return f"/keyframes/{video_id}/{frame_id}.jpg"


def keyframe_thumbnail_url(video_id: str, frame_id: int, *, backend_host: str) -> str:
    """Absolute thumbnail URL for clients that need a full URL."""
    return f"{backend_host.rstrip('/')}{keyframe_thumbnail_path(video_id, frame_id)}"


def keyframe_image_path(
    video_id: str,
    keyframe_id: int,
    *,
    keyframes_dir: Path,
) -> Path:
    """On-disk JPG path for a keyframe index (n), not submission frame_id."""
    return keyframes_dir / video_id / f"{keyframe_id:03d}.jpg"
