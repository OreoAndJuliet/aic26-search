from pathlib import Path
from typing import Any

from google import genai
from google.genai import types

from app.core.config import settings


class VQAEngine:
    def __init__(self) -> None:
        if not settings.GEMINI_API_KEY:
            raise RuntimeError("Missing GEMINI_API_KEY in environment.")
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self.model = self._normalize_model_name(settings.GEMINI_MODEL)

    @staticmethod
    def _normalize_model_name(model_name: str) -> str:
        normalized = model_name.strip().strip('"').strip("'")
        if normalized.startswith("models/"):
            normalized = normalized[len("models/") :]
        if not normalized:
            raise RuntimeError("Missing GEMINI_MODEL in environment.")
        return normalized

    def _answer_image(self, image_path: Path, question: str) -> str:
        if not image_path.is_file():
            return ""

        with image_path.open("rb") as image_file:
            image_bytes = image_file.read()

        mime_type = "image/jpeg"
        if image_path.suffix.lower() == ".png":
            mime_type = "image/png"

        response = self.client.models.generate_content(
            model=self.model,
            contents=[
                (
                    "Answer using only the image. Return only a concise answer "
                    "(max 100 chars). "
                    f"Question: {question}"
                ),
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            ],
        )

        text = (response.text or "").strip()
        return text[:100]

    def answer_single_image(self, image_path: Path, question: str) -> str:
        """Answer one image question for the JSON-to-VLM fallback path."""
        return self._answer_image(image_path, question)

    def answer(self, top_kis_results: list[dict[str, Any]], question: str):
        if not question.strip():
            return []

        processed_results = []
        for res in top_kis_results:
            frame_val = res.get("keyframe_id") if "keyframe_id" in res else res.get("frame_id", 0)
            image_path = Path(settings.STATIC_DIR) / "keyframes" / res["video_id"] / (
                f"{int(frame_val):03d}.jpg"
            )
            res_copy = res.copy()
            res_copy["answer"] = self._answer_image(image_path, question)
            processed_results.append(res_copy)

        return processed_results


vqa_engine = VQAEngine()
