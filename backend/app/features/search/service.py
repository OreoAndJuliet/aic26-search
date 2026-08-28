"""Unified POST /api/v1/search orchestration for KIS, VQA, and TRAKE."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Literal
from uuid import uuid4

from app.core.config import settings
from app.core.exceptions import InvalidQueryError
from app.features.search.contract import build_unified_search_response
from app.features.search.retrieval import run_kis_retrieval
from app.features.vqa.service import answer_vqa_question
from app.services.trake_engine import trake_engine
from app.services.translator import translator

logger = logging.getLogger(__name__)


async def _translate_events(events: list[str]) -> tuple[list[str], bool, float]:
    started_at = time.perf_counter()
    translated_events: list[str] = []
    translation_applied = False
    for event in events:
        try:
            parsed_intent = None
            try:
                from app.algorithms.human_intent_nlu import parse_human_intent
                parsed_intent = parse_human_intent(event)
            except Exception as exc:
                logger.debug("Human intent NLU error in TRAKE: %s", exc)

            translation = await translator.translate_async(event)
            en_text = translation.text
            
            if parsed_intent and parsed_intent.enriched_english_prompt:
                if parsed_intent.enriched_english_prompt.lower() not in en_text.lower():
                    en_text = f"{en_text} ({parsed_intent.enriched_english_prompt})"
                    
            translated_events.append(en_text)
            translation_applied = translation_applied or translation.applied
        except Exception as exc:
            logger.warning("Event translation failed for '%s', falling back to original: %s", event, exc)
            translated_events.append(event)
    translation_time_ms = round((time.perf_counter() - started_at) * 1000, 2)
    return translated_events, translation_applied, translation_time_ms


async def run_search(
    *,
    task_type: Literal["KIS", "VQA", "TRAKE"],
    query: str,
    question: str | None,
    top_k: int,
    events: list[str] | None = None,
    top_k_per_event: int = 60,
    max_gap_seconds: float = 300.0,
    video_filter: str | None = None,
    request_id: str | None = None,
) -> dict:
    if not query.strip() and not events:
        raise InvalidQueryError("Query text or events are required.")

    request_id = request_id or uuid4().hex
    started_at = time.perf_counter()
    response_extras: dict[str, object] = {}

    # Auto-detect video filter in query if not explicitly passed (e.g. "L23 xe buýt", "video L23_V005")
    clean_query = query
    if not video_filter:
        import re
        vid_match = re.search(r"\b(L\d{1,2}(?:_V\d{3})?)\b", query, re.IGNORECASE)
        if vid_match:
            video_filter = vid_match.group(1).upper()
            clean_query = re.sub(r"\b(L\d{1,2}(?:_V\d{3})?)\b", "", query, flags=re.IGNORECASE).strip()
            # Clean up residual words like "video", "trong"
            clean_query = re.sub(r"\b(video|trong|tại|ở)\b", "", clean_query, flags=re.IGNORECASE).strip()
            if not clean_query:
                clean_query = query
            logger.info("Auto-detected video filter from query: %s, cleaned query: '%s'", video_filter, clean_query)

    # Auto-detect TRAKE sequence in KIS mode
    if task_type == "KIS" and not events:
        trake_markers = [
            "bắt đầu", "kết thúc", "sau đó", "tiếp theo", "tiếp đến", "rồi", "cuối cùng",
            "starts with", "ends with", "then", "next", "after that", "finally", "subsequently"
        ]
        import re
        parts = [p.strip() for p in re.split(r'\.(?=\s|$)', clean_query) if p.strip()]
        
        has_marker = any(marker in clean_query.lower() for marker in trake_markers)
        has_multiple_sentences = len(parts) >= 2
        
        # [DISABLED] Do not auto-upgrade KIS to TRAKE. It breaks KIS queries with 3 sentences.
        # if (has_marker and has_multiple_sentences) or len(parts) >= 3:
        #     logger.info("Auto-upgrading KIS to TRAKE due to sequential markers or multi-sentence paragraph. Parts: %s", len(parts))
        #     task_type = "TRAKE"
        #     events = parts

    if task_type == "TRAKE":
        trake_events = events or [clean_query.strip()]
        translated_events, translation_applied, translation_time_ms = await _translate_events(
            trake_events
        )
        en_text = " | ".join(translated_events)
        response_extras["events"] = trake_events
        response_extras["translated_events"] = translated_events
    else:
        # Colloquial Vietnamese NLU & Cultural Intent Parsing
        parsed_intent = None
        try:
            from app.algorithms.human_intent_nlu import parse_human_intent
            parsed_intent = parse_human_intent(clean_query)
        except Exception as exc:
            logger.debug("Human intent NLU error: %s", exc)

        try:
            translation = await asyncio.wait_for(
                translator.translate_async(clean_query),
                timeout=4.0,
            )
            translation_time_ms = round((time.perf_counter() - started_at) * 1000, 2)
            en_text = translation.text
            translation_applied = translation.applied
        except Exception as exc:
            logger.warning("Translation failed or timed out for '%s', falling back to NLU / original query: %s", clean_query, exc)
            en_text = clean_query
            translation_applied = False
            translation_time_ms = round((time.perf_counter() - started_at) * 1000, 2)

        if parsed_intent and parsed_intent.enriched_english_prompt:
            if parsed_intent.enriched_english_prompt.lower() not in en_text.lower():
                en_text = f"{en_text} ({parsed_intent.enriched_english_prompt})"

        # Landmark & Encyclopedic Query Enrichment
        try:
            from app.services.encyclopedic_store import encyclopedic_store
        except Exception as exc:
            logger.debug("Landmark query enrichment failed: %s", exc)

        # Append Cultural Attire / Action Descriptors to English query
        try:
            if 'parsed_intent' in locals() and parsed_intent.enriched_english_prompt:
                if parsed_intent.enriched_english_prompt.lower() not in en_text.lower():
                    en_text = f"{en_text} ({parsed_intent.enriched_english_prompt})".strip()
        except Exception as exc:
            logger.debug("Cultural intent enrichment failed: %s", exc)

    results: list[dict] = []
    metrics: dict[str, float | dict | None] = {
        "embedding_time_ms": 0.0,
        "faiss_time_ms": 0.0,
        "metadata_time_ms": 0.0,
        "retrieval_time_ms": 0.0,
        "vlm_time_ms": 0.0,
        "rscore": None,
    }

    if task_type == "KIS":
        results, metrics = run_kis_retrieval(en_text, top_k, raw_query=query, video_filter=video_filter)
    elif task_type == "VQA":
        try:
            top_kis, metrics = run_kis_retrieval(en_text, top_k=top_k, raw_query=query, video_filter=video_filter)
            metrics["rscore"] = None
            results, metrics["vlm_time_ms"] = answer_vqa_question(top_kis, question or "")
        except (RuntimeError, ValueError, OSError) as exc:
            # If VLM is explicitly unavailable, propagate so router returns 503 as expected in tests
            from app.core.exceptions import VLMUnavailableError

            if isinstance(exc, VLMUnavailableError):
                raise

            # VQA must not bring down the service for other unexpected errors in test environments
            logger.exception("vqa_pipeline_failed")
            results = []
            metrics = {"embedding_time_ms": 0.0, "faiss_time_ms": 0.0, "metadata_time_ms": 0.0, "retrieval_time_ms": 0.0, "vlm_time_ms": 0.0, "rscore": None}
    elif task_type == "TRAKE":
        retrieval_started_at = time.perf_counter()
        results, trake_meta = trake_engine.align_events(
            translated_events,
            original_events=trake_events,
            top_k_per_event=top_k_per_event,
            max_gap_seconds=max_gap_seconds,
        )
        metrics["retrieval_time_ms"] = round((time.perf_counter() - retrieval_started_at) * 1000, 2)
        response_extras["trake"] = trake_meta
        
        # Log helpful error information if TRAKE failed
        if not results and trake_meta.get("error"):
            logger.warning(
                "request_id=%s TRAKE alignment failed: %s. Suggestion: %s",
                request_id,
                trake_meta.get("error"),
                trake_meta.get("suggestion"),
            )
    else:
        raise InvalidQueryError(f"Unsupported search type: {task_type}")

    total_time_ms = round((time.perf_counter() - started_at) * 1000, 2)

    response = build_unified_search_response(
        task_type=task_type,
        query=query,
        question=question,
        results=results,
        backend_host=settings.BACKEND_HOST,
        request_id=request_id,
        translated_text=en_text,
        translation_applied=translation_applied,
        translation_time_ms=translation_time_ms,
        total_time_ms=total_time_ms,
        default_answer=None,
        metrics=metrics,
        response_extras=response_extras,
    )

    logger.info(
        "request_id=%s endpoint=/api/v1/search type=%s total_time_ms=%s "
        "translation_time_ms=%s retrieval_time_ms=%s vlm_time_ms=%s result_count=%s",
        request_id,
        task_type,
        total_time_ms,
        translation_time_ms,
        metrics["retrieval_time_ms"],
        metrics["vlm_time_ms"],
        len(results),
    )
    return response
