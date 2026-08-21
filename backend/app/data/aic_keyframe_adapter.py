import csv
from pathlib import Path
from typing import ClassVar


class AICKeyframeAdapter:
    """Own the known AIC keyframe-map schema at one integration boundary."""

    REQUIRED_COLUMNS: ClassVar[set[str]] = {"n", "frame_idx", "pts_time"}

    def __init__(self, map_root: Path, keyframes_root: Path) -> None:
        self.map_root = Path(map_root)
        self.keyframes_root = Path(keyframes_root)
        
        # Make paths relative to current working directory for portability
        if not self.map_root.is_absolute():
            self.map_root = Path.cwd() / self.map_root
        if not self.keyframes_root.is_absolute():
            self.keyframes_root = Path.cwd() / self.keyframes_root

    def available_videos(self) -> set[str]:
        if self.map_root.is_dir():
            return {path.stem for path in self.map_root.glob("**/*.csv")}
        if self.keyframes_root.is_dir():
            return {path.name for path in self.keyframes_root.iterdir() if path.is_dir()}
        return set()

    def load_keyframe_map(self, video_id: str) -> list[dict[str, str]]:
        matches = list(self.map_root.glob(f"**/{video_id}.csv"))
        if len(matches) != 1:
            raise FileNotFoundError(
                f"Expected exactly one map file for {video_id}, found {len(matches)}."
            )
        with matches[0].open("r", encoding="utf-8", newline="") as map_file:
            reader = csv.DictReader(map_file)
            if not reader.fieldnames or not self.REQUIRED_COLUMNS.issubset(reader.fieldnames):
                raise ValueError(f"Invalid keyframe map schema: {matches[0]}")
            rows = list(reader)
        if not rows:
            raise ValueError(f"Keyframe map contains no rows: {matches[0]}")
        return rows

    def metadata_record(
        self, vector_id: int, video_id: str, map_row: dict[str, str], feature_path: Path
    ) -> dict:
        try:
            keyframe_id = int(map_row["n"])
            frame_id = int(map_row["frame_idx"])
            timestamp = float(map_row["pts_time"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Invalid map row for video {video_id}.") from exc

        image_path = self.keyframes_root / video_id / f"{keyframe_id:03d}.jpg"
        if image_path.is_file():
            try:
                relative_image_path = image_path.relative_to(self.keyframes_root.parent)
            except ValueError:
                relative_image_path = Path("keyframes") / video_id / f"{keyframe_id:03d}.jpg"
        else:
            relative_image_path = Path("keyframes") / video_id / f"{keyframe_id:03d}.jpg"

        return {
            "vector_id": vector_id,
            "video_id": video_id,
            "keyframe_id": keyframe_id,
            "frame_id": frame_id,
            "timestamp": timestamp,
            "image_path": relative_image_path.as_posix(),
            "feature_path": Path(feature_path).as_posix(),
        }

