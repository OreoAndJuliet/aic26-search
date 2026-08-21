"""Normalize search API payloads to the Frontend integration contract."""

from __future__ import annotations

from typing import Any

from app.utils.keyframes import keyframe_thumbnail_path, keyframe_thumbnail_url

UNIFIED_SEARCH_RESPONSE_KEYS = frozenset(
    {
        "status",
        "type",
        "request_id",
        "query",
        "question",
        "translated_query",
        "translated_text",
        "translation_applied",
        "results",
        "translation_time_ms",
        "retrieval_time_ms",
        "embedding_time_ms",
        "faiss_time_ms",
        "metadata_time_ms",
        "vlm_time_ms",
        "total_time_ms",
        "latency_ms",
        "rscore",
        "events",
        "translated_events",
        "trake",
    }
)


_DEFAULT_SENTINEL = object()


def normalize_search_result(
    item: dict[str, Any],
    *,
    backend_host: str,
    answer: str | None | object = _DEFAULT_SENTINEL,
) -> dict[str, Any]:
    """Ensure each result exposes video_id, frame_id, thumbnail_url, and answer."""
    video_id = str(item["video_id"])
    frame_id = int(item["frame_id"])
    thumbnail_path = keyframe_thumbnail_path(video_id, frame_id)

    if answer is _DEFAULT_SENTINEL:
        resolved_answer = item.get("answer")
    else:
        resolved_answer = answer

    normalized: dict[str, Any] = {
        "video_id": video_id,
        "frame_id": frame_id,
        "thumbnail_url": keyframe_thumbnail_url(video_id, frame_id, backend_host=backend_host),
        "answer": resolved_answer,
        "image_url": keyframe_thumbnail_url(video_id, frame_id, backend_host=backend_host),
    }

    for key, value in item.items():
        if key not in normalized:
            normalized[key] = value

    return normalized


def normalize_search_results(
    items: list[dict[str, Any]],
    *,
    backend_host: str,
    default_answer: str | None = None,
) -> list[dict[str, Any]]:
    return [
        normalize_search_result(
            item,
            backend_host=backend_host,
            answer=item.get("answer", default_answer),
        )
        for item in items
    ]


def build_unified_search_response(
    *,
    task_type: str,
    query: str,
    question: str | None,
    results: list[dict[str, Any]],
    backend_host: str,
    request_id: str,
    translated_text: str,
    translation_applied: bool,
    translation_time_ms: float,
    total_time_ms: float,
    default_answer: str | None = None,
    metrics: dict[str, Any] | None = None,
    response_extras: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Single response envelope for POST /api/v1/search across KIS, VQA, and TRAKE."""
    metric_values = metrics or {}
    payload: dict[str, Any] = {
        "status": "success",
        "type": task_type,
        "request_id": request_id,
        "query": query,
        "question": question,
        "translated_query": translated_text,
        "translated_text": translated_text,
        "translation_applied": translation_applied,
        "results": (normalized_results := normalize_search_results(
            results,
            backend_host=backend_host,
            default_answer=default_answer,
        )),
        "data": normalized_results,
        "translation_time_ms": translation_time_ms,
        "retrieval_time_ms": float(metric_values.get("retrieval_time_ms", 0.0)),
        "embedding_time_ms": float(metric_values.get("embedding_time_ms", 0.0)),
        "faiss_time_ms": float(metric_values.get("faiss_time_ms", 0.0)),
        "metadata_time_ms": float(metric_values.get("metadata_time_ms", 0.0)),
        "vlm_time_ms": float(metric_values.get("vlm_time_ms", 0.0)),
        "total_time_ms": total_time_ms,
        "latency_ms": total_time_ms,
        "rscore": metric_values.get("rscore"),
        "events": None,
        "translated_events": None,
        "trake": None,
    }
    if response_extras:
        payload.update(response_extras)
    return payload


def build_search_response(
    results: list[dict[str, Any]],
    *,
    backend_host: str,
    request_id: str | None = None,
    default_answer: str | None = None,
    extras: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Backward-compatible wrapper for callers that still pass loose extras."""
    from uuid import uuid4

    extras = extras or {}
    return build_unified_search_response(
        task_type=str(extras.get("type", "KIS")),
        query=str(extras.get("query", "")),
        question=extras.get("question"),
        results=results,
        backend_host=backend_host,
        request_id=request_id or uuid4().hex,
        translated_text=str(extras.get("translated_text", extras.get("translated_query", ""))),
        translation_applied=bool(extras.get("translation_applied", False)),
        translation_time_ms=float(extras.get("translation_time_ms", 0.0)),
        total_time_ms=float(extras.get("total_time_ms", extras.get("latency_ms", 0.0))),
        default_answer=default_answer,
        metrics={
            "retrieval_time_ms": extras.get("retrieval_time_ms", 0.0),
            "embedding_time_ms": extras.get("embedding_time_ms", 0.0),
            "faiss_time_ms": extras.get("faiss_time_ms", 0.0),
            "metadata_time_ms": extras.get("metadata_time_ms", 0.0),
            "vlm_time_ms": extras.get("vlm_time_ms", 0.0),
            "rscore": extras.get("rscore"),
        },
    )
