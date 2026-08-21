"""R-Score helpers for internal retrieval-quality monitoring.

These metrics map CLIP cosine similarity to [0, 1] and aggregate averages over
top-k buckets. They are useful while tuning retrieval, but they are NOT the
official AIC competition score. Use ``app.services.aic_grading`` and
``python -m scripts.eval_competition`` for organizer-style grading.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

DEFAULT_RSCORE_K_VALUES: tuple[int, ...] = (1, 5, 20, 50, 100)


def cosine_to_r_score(raw_cosine: float) -> float:
    """Map cosine similarity [-1, 1] to R-Score [0, 1]."""
    return max(0.0, min(1.0, (float(raw_cosine) + 1.0) / 2.0))


def result_r_score(result: dict[str, Any]) -> float:
    if "r_score" in result:
        return max(0.0, min(1.0, float(result["r_score"])))
    if "raw_cosine_score" in result:
        return cosine_to_r_score(float(result["raw_cosine_score"]))
    return max(0.0, min(1.0, float(result.get("score", 0.0))))


def compute_top_k_r_scores(
    results: Sequence[dict[str, Any]],
    k_values: Sequence[int] = DEFAULT_RSCORE_K_VALUES,
) -> dict[str, float]:
    """Average R-Score of the top-k ranked results for each k."""
    if not results:
        return {str(k): 0.0 for k in k_values}

    r_scores = [result_r_score(result) for result in results]
    top_k_r_scores: dict[str, float] = {}
    for k in k_values:
        bucket = r_scores[: min(int(k), len(r_scores))]
        top_k_r_scores[str(k)] = sum(bucket) / len(bucket) if bucket else 0.0
    return top_k_r_scores


def compute_final_r_score(
    results: Sequence[dict[str, Any]],
    k_values: Sequence[int] = DEFAULT_RSCORE_K_VALUES,
) -> float:
    """Final score = mean of Top-k R-Score for k in {1, 5, 20, 50, 100}."""
    top_k_r_scores = compute_top_k_r_scores(results, k_values)
    if not top_k_r_scores:
        return 0.0
    return sum(top_k_r_scores.values()) / len(top_k_r_scores)


def build_rscore_report(
    results: Sequence[dict[str, Any]],
    k_values: Sequence[int] = DEFAULT_RSCORE_K_VALUES,
) -> dict[str, Any]:
    top_k_r_scores = compute_top_k_r_scores(results, k_values)
    final_r_score = compute_final_r_score(results, k_values)
    return {
        "k_values": [int(k) for k in k_values],
        "top_k_r_scores": top_k_r_scores,
        "final_r_score": round(final_r_score, 6),
        "result_count": len(results),
    }
