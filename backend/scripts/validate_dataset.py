"""Validate the configured FAISS index, metadata mapping, and keyframe files."""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.core.config import settings
from app.core.exceptions import DatasetValidationError
from app.vector.faiss_store import FaissVectorStore


def main() -> int:
    try:
        store = FaissVectorStore(settings.FAISS_INDEX_PATH, settings.METADATA_PATH)
        static_root = settings.STATIC_DIR.resolve()
        feature_root = settings.FEATURE_ROOT.resolve()
        missing_images = []
        missing_features = []
        for item in store.metadata:
            raw_img = str(item["image_path"])
            img_p = Path(raw_img)
            if img_p.is_absolute():
                image_path = img_p.resolve()
            else:
                image_path = (static_root / img_p).resolve()
            try:
                image_path.relative_to(static_root)
            except ValueError:
                missing_images.append(item["vector_id"])
                continue
            if not image_path.is_file():
                missing_images.append(item["vector_id"])
            raw_feat = str(item["feature_path"])
            feat_p = Path(raw_feat)
            if feat_p.is_absolute():
                feature_path = feat_p.resolve()
            else:
                feature_path = (feature_root / feat_p).resolve()
            try:
                feature_path.relative_to(feature_root)
            except ValueError:
                missing_features.append(item["vector_id"])
                continue
            if not feature_path.is_file():
                missing_features.append(item["vector_id"])
        if missing_images:
            raise DatasetValidationError(
                f"{len(missing_images)} metadata records reference missing or unsafe image files."
            )
        if missing_features:
            raise DatasetValidationError(
                f"{len(missing_features)} metadata records reference missing or unsafe feature files."
            )
    except DatasetValidationError as exc:
        print(json.dumps({"status": "invalid", "error": exc.message}))
        return 1

    print(
        json.dumps(
            {
                "status": "valid",
                "dimension": store.stats.dimension,
                "vector_count": store.stats.vector_count,
                "metadata_count": store.stats.metadata_count,
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
