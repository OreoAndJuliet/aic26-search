import glob
import json
from pathlib import Path

import faiss
import numpy as np

from app.core.config import settings
from app.data.aic_keyframe_adapter import AICKeyframeAdapter


def build_real_faiss_index() -> None:
    # Validate required directories exist
    required_dirs = {
        "MAP_ROOT": settings.MAP_ROOT,
        "KEYFRAMES_DIR": settings.KEYFRAMES_DIR,
        "FEATURE_ROOT": settings.FEATURE_ROOT,
        "DATA_DIR": settings.DATA_DIR
    }
    
    for dir_name, dir_path in required_dirs.items():
        dir_path.mkdir(parents=True, exist_ok=True)
    
    dataset = AICKeyframeAdapter(settings.MAP_ROOT, settings.KEYFRAMES_DIR)
    available_videos = dataset.available_videos()

    print("Scanning feature files...")
    npy_files = sorted(
        glob.glob(str(settings.FEATURE_ROOT / "**" / "*.npy"), recursive=True)
    )

    if not npy_files:
        print("No .npy files found. Ensure features are extracted into data/features/.")
        return

    all_vectors = []
    metadata = []
    current_vector_idx = 0
    expected_dimension = None

    for npy_path in npy_files:
        video_id = Path(npy_path).stem
        if video_id not in available_videos:
            continue

        features = np.load(npy_path).astype("float32")
        if features.ndim != 2 or features.shape[0] == 0:
            raise ValueError(f"Feature file must be a non-empty 2D array: {npy_path}")
        if not np.isfinite(features).all():
            raise ValueError(f"Feature file contains non-finite values: {npy_path}")
        if expected_dimension is None:
            expected_dimension = features.shape[1]
        elif features.shape[1] != expected_dimension:
            raise ValueError(
                f"Feature dimension mismatch for {npy_path}: "
                f"expected {expected_dimension}, got {features.shape[1]}."
            )
        faiss.normalize_L2(features)
        all_vectors.append(features)

        keyframe_map = dataset.load_keyframe_map(video_id)
        if len(features) != len(keyframe_map):
            raise ValueError(
                f"Feature/map row mismatch for {video_id}: "
                f"{len(features)} features, {len(keyframe_map)} map rows."
            )

        for map_row in keyframe_map:
            metadata.append(
                dataset.metadata_record(
                    current_vector_idx,
                    video_id,
                    map_row,
                    Path(npy_path),
                )
            )
            current_vector_idx += 1

    if not all_vectors:
        raise ValueError("No feature files match the available keyframe videos.")

    full_matrix = np.vstack(all_vectors)
    dimension = full_matrix.shape[1]

    print(f"Loaded {full_matrix.shape[0]} vectors ({dimension}-dimensional). Building FAISS index...")

    index = faiss.IndexFlatIP(dimension)
    index.add(full_matrix)

    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(settings.FAISS_INDEX_PATH))

    with settings.METADATA_PATH.open("w", encoding="utf-8") as file:
        json.dump(metadata, file, ensure_ascii=False, indent=2)

    print(f"FAISS index successfully built at {settings.FAISS_INDEX_PATH}.")


if __name__ == "__main__":
    build_real_faiss_index()
