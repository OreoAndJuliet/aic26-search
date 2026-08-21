"""VQA execution engine: visual reasoning with spatial attention, zooming, storyboards & visual hash cache."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from PIL import Image

from app.cache.factory import create_cache_backend
from app.cache.visual_hash_cache import lookup_visual_cache, store_visual_cache
from app.cache.vlm_cache import VlmCache
from app.core.config import settings
from app.providers.vlm import VLMProvider, create_vlm_provider

logger = logging.getLogger(__name__)

from app.utils.vqa_answer import parse_vqa_answer

# Standard instruction appended to questions when calling VLMs.
VQA_INSTRUCTION = (
    "Answer concisely in 1 to 3 words. State only the direct answer. "
    "Do not explain. Do not write full sentences."
)


def build_vqa_prompt(question: str) -> str:
    """Combine the user's question with formatting instructions for the VLM."""
    cleaned_question = question.strip()
    if not cleaned_question.endswith("?"):
        cleaned_question += "?"
    return f"Question: {cleaned_question}\nInstruction: {VQA_INSTRUCTION}"





class VQAEngine:
    def __init__(self) -> None:
        self._answer_cache = VlmCache(
            backend=create_cache_backend(namespace="vlm"),
            scope="vlm_answers",
            ttl_seconds=settings.VLM_CACHE_TTL_SECONDS,
        )
        self._provider: VLMProvider | None = None

    def _ensure_provider(self) -> VLMProvider:
        if self._provider is None:
            self._provider = create_vlm_provider(
                provider_name=settings.VQA_PROVIDER,
                provider_mode=settings.AI_PROVIDER_MODE,
                timeout_seconds=settings.VQA_TIMEOUT_SECONDS,
                gemini_api_key=settings.GEMINI_API_KEY,
                gemini_model_name=settings.GEMINI_MODEL,
                gemini_api_base=settings.GEMINI_API_BASE,
                openai_api_key=settings.OPENAI_API_KEY,
                openai_model_name=settings.OPENAI_VQA_MODEL,
                openai_api_base=settings.OPENAI_API_BASE,
                anthropic_api_key=settings.ANTHROPIC_API_KEY,
                claude_model_name=settings.CLAUDE_VQA_MODEL,
                anthropic_api_base=settings.ANTHROPIC_API_BASE,
                qwen_api_key=settings.QWEN_API_KEY,
                qwen_model_name=settings.QWEN_VQA_MODEL,
                qwen_api_base=settings.QWEN_API_BASE,
            )
        return self._provider

    def warm_up(self) -> None:
        """Pre-initialize VLM provider and object store to eliminate cold-start latency."""
        try:
            self._ensure_provider()
            from app.services.object_store import object_store
            object_store.warm_up()
            logger.info("vqa_engine warmup complete (VLM provider & ObjectStore primed)")
        except Exception as exc:
            logger.warning("vqa_engine warmup warning: %s", exc)

    def _answer_image(
        self,
        image_path: Path,
        question: str,
        video_id: str = "",
        keyframe_id: int = 0,
    ) -> str:
        cached = self._answer_cache.get(
            video_id=video_id,
            keyframe_id=keyframe_id,
            question=question,
        )
        if cached is not None:
            return cached

        # Check Perceptual Visual Hash (dHash) cache
        if image_path.is_file():
            try:
                with Image.open(image_path) as img:
                    p_cached = lookup_visual_cache(question, img)
                    if p_cached is not None:
                        return p_cached
            except Exception as exc:
                logger.debug("Visual hash lookup error: %s", exc)

        provider = self._ensure_provider()
        raw_answer = provider.answer(image_path, question)
        answer = parse_vqa_answer(raw_answer)

        self._answer_cache.set(
            video_id=video_id,
            keyframe_id=keyframe_id,
            question=question,
            answer=answer,
        )

        # Store into Perceptual Visual Hash cache
        if image_path.is_file():
            try:
                with Image.open(image_path) as img:
                    store_visual_cache(question, img, answer)
            except Exception as exc:
                logger.debug("Visual hash store error: %s", exc)

        return answer

    def answer_single_image(self, image_path: Path, question: str) -> str:
        """Answer one image question for the JSON-to-VLM fallback path."""
        parts = image_path.parts
        video_id = parts[-2] if len(parts) >= 2 else ""
        stem = Path(parts[-1]).stem if parts else ""
        keyframe_id = int(stem) if stem.isdigit() else 0
        return self._answer_image(
            image_path,
            question,
            video_id=video_id,
            keyframe_id=keyframe_id,
        )

    def answer(self, top_kis_results: list[dict[str, Any]], question: str) -> list[dict[str, Any]]:
        if not question.strip() or not top_kis_results:
            return []

        from app.algorithms.spatial_attention import (
            get_spatial_focused_image,
            parse_spatial_quadrant,
        )
        from app.algorithms.temporal_vqa import (
            build_temporal_storyboard,
            is_dynamic_action_question,
        )
        from app.algorithms.visual_zooming import (
            detect_micro_target,
            extract_high_res_object_crop,
        )
        from app.algorithms.vqa_distillation import build_saliency_focused_prompt
        from app.services.kis_engine import kis_engine
        from app.services.object_store import object_store

        # Check if question is a dynamic action, spatial directive, or micro-object query
        is_dynamic_action = (
            is_dynamic_action_question(question)
            if settings.TEMPORAL_VQA_CONTEXT_ENABLED
            else False
        )
        quad_name, quad_coords = (
            parse_spatial_quadrant(question)
            if settings.SPATIAL_VQA_ATTENTION_ENABLED and not is_dynamic_action
            else (None, None)
        )
        micro_target = detect_micro_target(question)

        def _evaluate_candidate(result: dict[str, Any]) -> dict[str, Any]:
            keyframe_id = int(result.get("keyframe_id", result.get("frame_id", 0)))
            video_id = str(result["video_id"])

            image_path_raw = kis_engine.resolve_keyframe_path(video_id, keyframe_id)
            if image_path_raw is not None:
                image_path = Path(image_path_raw)
                if not image_path.is_absolute():
                    image_path = Path(settings.STATIC_DIR) / image_path
            else:
                image_path = settings.KEYFRAMES_DIR / video_id / f"{keyframe_id:03d}.jpg"

            result_copy = result.copy()
            eval_question = question

            # 1. Temporal Storyboard for dynamic action questions
            if is_dynamic_action:
                storyboard_path = build_temporal_storyboard(
                    video_id,
                    keyframe_id,
                    settings.KEYFRAMES_DIR,
                )
                if storyboard_path and storyboard_path.is_file():
                    eval_image_path = storyboard_path
                    eval_question = (
                        f"This image is a temporal sequence [Before (t-1), Target Event (t0), After (t+1)] "
                        f"from the video. Based on the motion and progression over time, answer concisely: {question}"
                    )
                    result_copy["temporal_context"] = True
                else:
                    eval_image_path = image_path

            # 2. Dynamic Multi-Scale Visual Zooming for micro-objects
            elif micro_target:
                zoomed_path = None
                boxes = object_store.find_by_class(video_id, keyframe_id, micro_target)
                if boxes:
                    best_box = boxes[0]["box"]
                    zoomed_path = extract_high_res_object_crop(image_path, best_box)

                if zoomed_path and zoomed_path.is_file():
                    eval_image_path = zoomed_path
                    result_copy["visual_zoom"] = micro_target
                    eval_question = build_saliency_focused_prompt(question)
                else:
                    eval_image_path = image_path
                    eval_question = build_saliency_focused_prompt(question)

            # 3. Spatial Quadrant Cropping for directional queries
            elif quad_name:
                eval_image_path = get_spatial_focused_image(image_path, quad_name, quad_coords)
                result_copy["spatial_quadrant"] = quad_name
                eval_question = build_saliency_focused_prompt(question)

            # 4. Standard Keyframe Evaluation with Interrogative Saliency Distillation
            else:
                eval_image_path = image_path
                eval_question = build_saliency_focused_prompt(question)

            try:
                result_copy["answer"] = self._answer_image(
                    eval_image_path,
                    eval_question,
                    video_id=video_id,
                    keyframe_id=keyframe_id,
                )
            except Exception as exc:
                result_copy["answer"] = ""
                result_copy["vlm_error"] = str(exc)

            result_copy["source"] = "VLM_API"
            return result_copy

        max_workers = min(len(top_kis_results), settings.VQA_MAX_CONCURRENCY)
        if max_workers <= 1:
            return [_evaluate_candidate(r) for r in top_kis_results]

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            return list(executor.map(_evaluate_candidate, top_kis_results))


vqa_engine = VQAEngine()
