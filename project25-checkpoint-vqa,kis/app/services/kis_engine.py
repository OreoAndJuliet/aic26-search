import json
import os

import faiss
import torch
from sentence_transformers import SentenceTransformer

from app.core.config import settings


class KISEngine:
    def __init__(self):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model: SentenceTransformer | None = None
        self.model_load_error: str | None = None

        print("Loading FAISS index and metadata...")
        if os.path.exists(settings.FAISS_INDEX_PATH) and os.path.exists(settings.METADATA_PATH):
            self.index = faiss.read_index(settings.FAISS_INDEX_PATH)
            with open(settings.METADATA_PATH, "r", encoding="utf-8") as f:
                self.metadata = json.load(f)
        else:
            self.index = None
            self.metadata = []

    def _ensure_model_loaded(self) -> None:
        if self.model is not None:
            return
        if self.model_load_error is not None:
            raise RuntimeError(self.model_load_error)

        print("Loading Sentence Transformers CLIP text encoder...")
        try:
            self.model = SentenceTransformer(
                settings.CLIP_MODEL_NAME,
                device=self.device,
                model_kwargs={"low_cpu_mem_usage": True},
            )
        except OSError as exc:
            self.model_load_error = (
                "Failed to load CLIP model due to insufficient memory/page file. "
                "Increase Windows virtual memory (paging file) and retry."
            )
            raise RuntimeError(self.model_load_error) from exc

    def search(self, english_text: str, top_k: int = 50):
        if self.index is None or self.index.ntotal == 0:
            return []
        
        if top_k < 1:
            raise ValueError("top_k must be at least 1")

        top_k = min(top_k, self.index.ntotal)
        
        self._ensure_model_loaded()

        # 1. Đưa text qua CLIP Text Encoder.  FAISS contains L2-normalized
        # image features, so normalize the query for cosine-similarity search.
        query_vector = self.model.encode(
            [english_text],
            normalize_embeddings=True,
            convert_to_numpy=True,
        ).astype("float32")

        
        
        # 2. Tìm kiếm trên FAISS Index
        scores, indices = self.index.search(query_vector, top_k)

        results = []

        for score, idx in zip(scores[0], indices[0]):
            if 0 <= idx < len(self.metadata):
                item = self.metadata[idx]
                v_id = item["video_id"]
                f_id = item["frame_id"]

        # keyframe_id is the JPEG filename number; frame_id is the original video frame.
                keyframe_id = item.get("keyframe_id", f_id)

                image_url = (
                    f"{settings.BACKEND_HOST}/static/keyframes/"
                    f"{v_id}/{int(keyframe_id):03d}.jpg"
                )

                raw_score = float(score)
                normalized_score = max(0.0, min(1.0, (raw_score + 1.0) / 2.0))

                results.append({
                    "video_id": v_id,
                    "frame_id": f_id,
                    "keyframe_id": int(keyframe_id),
                    "image_url": image_url,
                    "score": normalized_score,
                    "raw_cosine_score": raw_score,
                    "answer": None,
        })

        return results

kis_engine = KISEngine()
