import json
import math
from pathlib import Path
from typing import Any, ClassVar

from app.core.exceptions import DatasetValidationError


class MetadataCatalog:
    """Shared keyframe metadata loaded from metadata.json."""

    REQUIRED_METADATA_FIELDS: ClassVar[set[str]] = {
        "vector_id",
        "video_id",
        "keyframe_id",
        "frame_id",
        "timestamp",
        "image_path",
        "feature_path",
    }

    def __init__(self, metadata_path: Path) -> None:
        self._metadata_path = Path(metadata_path)
        self._metadata = self._read_metadata()
        self._frame_image_paths = self._build_frame_image_paths()
        self._frame_lookup = {
            (str(item["video_id"]).strip(), int(item["frame_id"])): item
            for item in self._metadata
        }

    def find_by_frame(self, video_id: str, frame_id: int) -> dict[str, Any] | None:
        """Fast O(1) lookup of metadata record by video_id and frame_id."""
        return self._frame_lookup.get((video_id.strip(), int(frame_id)))

    @property
    def metadata(self) -> tuple[dict[str, Any], ...]:
        return tuple(self._metadata)

    @property
    def metadata_count(self) -> int:
        return len(self._metadata)

    def __len__(self) -> int:
        return len(self._metadata)

    def metadata_for(self, vector_id: int) -> dict[str, Any]:
        if not 0 <= vector_id < len(self._metadata):
            raise DatasetValidationError("Vector ID is outside the metadata catalog.")
        return self._metadata[vector_id]

    def get(self, vector_id: int) -> dict[str, Any]:
        """Convenience alias for metadata_for."""
        return self.metadata_for(vector_id)

    def image_path_for_frame(self, video_id: str, frame_id: int) -> Path | None:
        image_path = self._frame_image_paths.get((video_id.strip(), int(frame_id)))
        if image_path is None:
            return None
        return Path(image_path)

    def validate_vector_count(self, vector_count: int) -> None:
        if vector_count != len(self._metadata):
            raise DatasetValidationError(
                "Vector count does not match the metadata row count."
            )
        self._validate_rows()

    def _read_metadata(self) -> list[dict[str, Any]]:
        if not self._metadata_path.is_file():
            raise DatasetValidationError("FAISS metadata file is missing.")
        try:
            with self._metadata_path.open("r", encoding="utf-8") as metadata_file:
                metadata = json.load(metadata_file)
        except (OSError, json.JSONDecodeError) as exc:
            raise DatasetValidationError("FAISS metadata file is malformed.") from exc
        if not isinstance(metadata, list):
            raise DatasetValidationError("FAISS metadata must be a JSON list.")
        return metadata

    def _build_frame_image_paths(self) -> dict[tuple[str, int], str]:
        lookup: dict[tuple[str, int], str] = {}
        for item in self._metadata:
            key = (str(item["video_id"]).strip(), int(item["frame_id"]))
            lookup[key] = str(item["image_path"])
        return lookup

    def _validate_rows(self) -> None:
        for expected_id, item in enumerate(self._metadata):
            if not isinstance(item, dict) or not self.REQUIRED_METADATA_FIELDS.issubset(item):
                raise DatasetValidationError(
                    f"Metadata row {expected_id} is missing required fields."
                )
            try:
                vector_id = int(item["vector_id"])
                frame_id = int(item["frame_id"])
                keyframe_id = int(item["keyframe_id"])
                timestamp = float(item["timestamp"])
            except (TypeError, ValueError) as exc:
                raise DatasetValidationError(
                    f"Metadata row {expected_id} contains invalid numeric values."
                ) from exc
            if vector_id != expected_id or frame_id < 0 or keyframe_id < 0:
                raise DatasetValidationError(
                    f"Metadata row {expected_id} has an invalid ID mapping."
                )
            if not math.isfinite(timestamp) or not str(item["video_id"]).strip():
                raise DatasetValidationError(
                    f"Metadata row {expected_id} has invalid required values."
                )
            if not str(item["image_path"]).strip():
                raise DatasetValidationError(f"Metadata row {expected_id} has no image path.")
            if not str(item["feature_path"]).strip():
                raise DatasetValidationError(f"Metadata row {expected_id} has no feature path.")
