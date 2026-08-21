"""Probe a KIS query and inspect specific frame vectors."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import numpy as np

from app.services.kis_engine import kis_engine


def load_npy_feature(feature_path: Path, keyframe_id: int) -> np.ndarray | None:
    if not feature_path.is_file():
        return None

    array = np.load(feature_path).astype(np.float32, copy=False)
    if array.ndim == 1:
        vector = array.reshape(-1)
    elif array.ndim == 2:
        row_index = max(int(keyframe_id) - 1, 0)
        if row_index >= array.shape[0]:
            return None
        vector = array[row_index].reshape(-1)
    else:
        return None

    norm = float(np.linalg.norm(vector))
    if norm <= 0:
        return None
    return vector / norm


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a.reshape(-1), b.reshape(-1)))


def main() -> int:
    query = sys.argv[1] if len(sys.argv) > 1 else "a person walking in a room"
    top_k = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    probe_video = sys.argv[3] if len(sys.argv) > 3 else None

    from app.features.search.retrieval import run_kis_retrieval
    kis_engine.initialize()
    store = kis_engine.store
    encoder = kis_engine.text_encoder

    results, metrics = run_kis_retrieval(query, top_k, raw_query=query)
    query_vector = kis_engine.encode_query_vector(query)

    print(json.dumps({"query": query, "metrics": metrics, "top_k": top_k}, indent=2))
    print("\nTop results:")
    for row in results[:10]:
        print(
            f"  rank={row['rank']:>3} score={row['score']:.4f} "
            f"{row['video_id']} frame={row['frame_id']} keyframe={row['keyframe_id']} "
            f"path={row.get('image_path', '')}"
        )

    if probe_video:
        matches = [
            item
            for item in store.metadata
            if str(item["video_id"]).upper() == probe_video.upper()
        ]
        if not matches:
            print(f"\nNo metadata rows for video_id={probe_video}")
            return 1
        print(f"\nProbing {len(matches)} frame(s) for video_id={probe_video}:")
        for item in matches[:5]:
            vector_id = int(item["vector_id"])
            image_path = Path(str(item["image_path"]))
            feature_path = Path(str(item["feature_path"]))
            stored = store.reconstruct(vector_id)
            live_image = encoder.encode_image(image_path).reshape(-1)
            npy = load_npy_feature(feature_path, int(item["keyframe_id"]))

            text_score = cosine(query_vector, stored)
            stored_live = cosine(stored, live_image)
            npy_stored = cosine(npy, stored) if npy is not None else None

            print(
                json.dumps(
                    {
                        "vector_id": vector_id,
                        "video_id": item["video_id"],
                        "keyframe_id": item["keyframe_id"],
                        "frame_id": item["frame_id"],
                        "image_path": str(image_path),
                        "feature_path": str(feature_path),
                        "faiss_search_score": next(
                            (
                                row["score"]
                                for row in results
                                if row["video_id"] == item["video_id"]
                                and row["frame_id"] == item["frame_id"]
                            ),
                            None,
                        ),
                        "query_vs_stored_cosine": round(text_score, 6),
                        "stored_vs_live_image_cosine": round(stored_live, 6),
                        "npy_vs_stored_cosine": round(npy_stored, 6) if npy_stored is not None else None,
                        "stored_norm": round(float(np.linalg.norm(stored)), 6),
                        "live_image_norm": round(float(np.linalg.norm(live_image)), 6),
                    },
                    indent=2,
                )
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
