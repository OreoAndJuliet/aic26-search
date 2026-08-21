"""Metadata-aware reranking for hybrid retrieval results."""

from __future__ import annotations

import re

from app.core.config import settings


def _tokenize(value: str | None) -> set[str]:
    if not value:
        return set()
    return {
        token
        for token in re.findall(r"[a-zA-Z0-9\u00C0-\uFFFF]+", value.casefold())
        if len(token) > 2
    }


def _result_text(item: dict) -> str:
    pieces = [
        item.get("video_id"),
        item.get("media_title"),
        item.get("media_channel"),
        item.get("media_description"),
        item.get("answer"),
        item.get("title"),
        item.get("description"),
        item.get("caption"),
        item.get("context"),
    ]
    return " ".join(str(piece) for piece in pieces if piece)


def metadata_overlap_score(query: str, result: dict) -> float:
    """Reward results whose metadata matches the query terms."""
    if not settings.HYBRID_METADATA_RERANK_ENABLED:
        return 0.0

    query_terms = _tokenize(query)
    if not query_terms:
        return 0.0

    metadata_terms = _tokenize(_result_text(result))
    overlap = query_terms & metadata_terms
    if not overlap:
        return 0.0

    return round((len(overlap) / max(len(query_terms), 1)) * settings.HYBRID_METADATA_RERANK_WEIGHT, 6)


def rerank_hybrid_results(
    query: str,
    results: list[dict],
    *,
    task_type: str = "KIS",
) -> list[dict]:
    """Apply metadata-aware reranking in a task-specific manner."""
    if not results:
        return results

    reranked: list[dict] = []
    for item in results:
        base_score = float(item.get("r_score", item.get("score", 0.0)))
        object_boost = float(item.get("object_boost", 0.0))
        media_boost = float(item.get("media_boost", 0.0))
        metadata_boost = metadata_overlap_score(query, item)
        overlap_count = len(_tokenize(query) & _tokenize(_result_text(item)))

        if task_type == "TRAKE":
            temporal_bonus = 0.02 if item.get("frame_id") is not None else 0.0
            final_score = base_score + object_boost + media_boost + metadata_boost + temporal_bonus
        elif task_type == "VQA":
            visual_bonus = 0.03 if item.get("answer") is not None else 0.0
            final_score = base_score + object_boost + media_boost + metadata_boost + visual_bonus
        else:
            final_score = base_score + object_boost + media_boost + metadata_boost

        copy = dict(item)
        copy["query_overlap"] = overlap_count
        copy["metadata_boost"] = round(metadata_boost, 6)
        copy["final_score"] = round(final_score, 6)
        reranked.append(copy)

    reranked.sort(
        key=lambda row: (
            -float(row.get("final_score", row.get("r_score", row.get("score", 0.0)))),
            int(row.get("rank", 999)),
        )
    )

    for rank, item in enumerate(reranked, start=1):
        item["rank"] = rank
    return reranked
