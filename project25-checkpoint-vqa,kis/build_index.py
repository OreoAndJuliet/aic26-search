import os
import json
import glob
import csv
import numpy as np
import faiss


def load_keyframe_map(map_dir: str, video_id: str):
    """Return the ordered AIC keyframe mapping for one video."""
    matches = glob.glob(os.path.join(map_dir, "**", f"{video_id}.csv"), recursive=True)
    if len(matches) != 1:
        raise FileNotFoundError(
            f"Expected exactly one map file for {video_id}, found {len(matches)}."
        )

    with open(matches[0], "r", encoding="utf-8", newline="") as map_file:
        rows = list(csv.DictReader(map_file))

    required_columns = {"n", "frame_idx"}
    if not rows or not required_columns.issubset(rows[0]):
        raise ValueError(f"Invalid keyframe map: {matches[0]}")
    return rows

def build_real_faiss_index():
    features_dir = os.path.join("data", "features")
    map_dir = os.path.join("data", "map_keyframes")
    keyframes_dir = os.path.join("static", "keyframes")
    available_videos = {
        name for name in os.listdir(keyframes_dir)
        if os.path.isdir(os.path.join(keyframes_dir, name))
    }
    
    print("Scanning feature files...")
    npy_files = sorted(glob.glob(os.path.join(features_dir, "**", "*.npy"), recursive=True))
    
    if not npy_files:
        print("No .npy files found. Make sure features are extracted into data/features/")
        return

    all_vectors = []
    metadata = []
    current_vector_idx = 0

    for npy_path in npy_files:
        video_id = os.path.splitext(os.path.basename(npy_path))[0]
        # Index only videos whose keyframes are available to this backend.
        # This prevents search results from returning broken thumbnail URLs.
        if video_id not in available_videos:
            continue

        # Load .npy array (N, 512)
        features = np.load(npy_path).astype("float32")
        faiss.normalize_L2(features)
        all_vectors.append(features)

        # Extract video_id from filename (e.g. L21_V001.npy -> L21_V001)
        # A feature row corresponds to the same row in the supplied AIC map.
        # `n` names the JPEG keyframe, while `frame_idx` is the original-video
        # frame number required for an AIC submission.  They are not equivalent.
        keyframe_map = load_keyframe_map(map_dir, video_id)
        if len(features) != len(keyframe_map):
            raise ValueError(
                f"Feature/map row mismatch for {video_id}: "
                f"{len(features)} features, {len(keyframe_map)} map rows."
            )

        for row_idx, map_row in enumerate(keyframe_map):
            metadata.append({
                "vector_id": current_vector_idx,
                "video_id": video_id,
                "keyframe_id": int(map_row["n"]),
                "frame_id": int(map_row["frame_idx"]),
            })
            current_vector_idx += 1

    # Stack all feature arrays into one big matrix
    full_matrix = np.vstack(all_vectors)
    dimension = full_matrix.shape[1]

    print(f"Loaded {full_matrix.shape[0]} total vectors ({dimension}-dimensional). Building FAISS index...")

    # Build FAISS Flat Inner Product Index (Cosine Similarity)
    index = faiss.IndexFlatIP(dimension)
    index.add(full_matrix)

    # Save to disk
    os.makedirs("data", exist_ok=True)
    faiss.write_index(index, os.path.join("data", "faiss_index.bin"))
    
    with open(os.path.join("data", "metadata.json"), "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    print("FAISS index successfully built at data/faiss_index.bin.")

if __name__ == "__main__":
    build_real_faiss_index()
