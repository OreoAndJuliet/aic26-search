from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.core.config import settings
from app.services.kis_engine import kis_engine
from app.services.media_info_store import media_info_store

router = APIRouter()


import csv
import functools


@functools.lru_cache(maxsize=1024)
def _resolve_keyframe_id_from_map(video_id: str, frame_id: int) -> int | None:
    """Find the sequential keyframe_id (n) for a given video_id and frame_idx (frame_id)."""
    # 1. Check data/map_keyframes/<video_id>.csv
    map_csv = settings.DATA_DIR / "map_keyframes" / f"{video_id}.csv"
    if not map_csv.is_file():
        csvs = list(settings.DATA_DIR.glob(f"**/{video_id}.csv"))
        if csvs:
            map_csv = csvs[0]

    if map_csv.is_file():
        try:
            with map_csv.open("r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    f_idx = int(row.get("frame_idx", -1))
                    if f_idx == frame_id:
                        return int(row.get("n", 1))
        except Exception:
            pass
    return None


@router.get("/keyframes/{video_id}/{frame_id}.jpg")
@router.head("/keyframes/{video_id}/{frame_id}.jpg")
def serve_keyframe_by_frame_id(video_id: str, frame_id: int) -> FileResponse:
    print(f"DEBUG: serve_keyframe_by_frame_id called for {video_id} {frame_id}")
    """Serve keyframe images using FE contract paths keyed by frame_id.

    Strategies:
    1. Ask KIS vector store for canonical image path.
    2. Convert frame_id -> keyframe_id via map_keyframes CSV.
    3. Direct path in KEYFRAMES_DIR (001.jpg, 166.jpg, etc.).
    4. Exact or numeric match scan.
    """
    # 1) Ask KIS store for canonical image path
    try:
        image_path_raw = kis_engine.resolve_keyframe_path(video_id, frame_id)
        if image_path_raw is not None:
            image_path = Path(image_path_raw)
            if not image_path.is_absolute():
                image_path = Path(settings.STATIC_DIR) / image_path
            if image_path.is_file():
                return FileResponse(path=image_path, media_type="image/jpeg")
    except Exception:
        pass

    # 2) Convert frame_id -> keyframe_id via map_keyframes CSV
    n = _resolve_keyframe_id_from_map(video_id, frame_id)
    if n is not None:
        for pattern in [f"{n:03d}.jpg", f"{n}.jpg", f"{n:04d}.jpg", f"{n:05d}.jpg"]:
            candidate = Path(settings.KEYFRAMES_DIR) / video_id / pattern
            if candidate.is_file():
                return FileResponse(path=candidate, media_type="image/jpeg")

    # 3) Direct candidate paths
    for pattern in [f"{frame_id}.jpg", f"{frame_id:03d}.jpg", f"{frame_id:04d}.jpg", f"{frame_id:05d}.jpg"]:
        static_candidate = Path(settings.KEYFRAMES_DIR) / video_id / pattern
        if static_candidate.is_file():
            return FileResponse(path=static_candidate, media_type="image/jpeg")

    # 4) Numeric match scan
    video_dir = Path(settings.KEYFRAMES_DIR) / video_id
    if video_dir.is_dir():
        for child in sorted(video_dir.iterdir()):
            if child.is_file() and child.suffix.lower() in {".jpg", ".jpeg", ".png"}:
                name = child.stem
                if name.isdigit() and int(name) == frame_id:
                    return FileResponse(path=child, media_type="image/jpeg")

    # 5) Legacy static directory fallback
    legacy_dir = Path(settings.STATIC_DIR) / "keyframes" / video_id
    if legacy_dir.is_dir():
        for child in sorted(legacy_dir.iterdir()):
            if child.is_file() and child.suffix.lower() in {".jpg", ".jpeg", ".png"}:
                if child.stem.isdigit() and int(child.stem) == frame_id:
                    return FileResponse(path=child, media_type="image/jpeg")

    # 6) Fallback placeholder if batch is not yet downloaded
    placeholder = Path(settings.STATIC_DIR) / "placeholder.jpg"
    if placeholder.is_file():
        return FileResponse(path=placeholder, media_type="image/jpeg")

    raise HTTPException(status_code=404, detail="Keyframe image not found.")


@router.get("/api/v1/videos/{video_id}/info")
async def video_info(video_id: str) -> dict:
    """Return optional YouTube metadata JSON for a video when available."""
    info = media_info_store.get(video_id)
    if info is None:
        raise HTTPException(status_code=404, detail="Video metadata not found.")
    return {"video_id": video_id, "metadata": info}
