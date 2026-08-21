"""Official AIC competition grading against ground-truth labels.

This module implements the organizer-style Mean of Top-k R-Score protocol:
  - Each ranked result gets R-Score in [0, 1] from *correctness* vs ground truth.
  - R@k = max R-Score among the top-k ranked results (not an average).
  - Final query score = mean(R@1, R@5, R@20, R@50, R@100).

The cosine-based metrics in ``kis_rscore.py`` are a separate internal retrieval
quality proxy and must not be used as competition scores.
"""

from __future__ import annotations

import csv
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_COMPETITION_K_VALUES: tuple[int, ...] = (1, 5, 20, 50, 100)


@dataclass(frozen=True)
class GroundTruthQuery:
    query_id: int
    task_type: str
    media_item_name: str
    frame_ranges: tuple[tuple[int, int], ...]
    answer: str | None = None


def normalize_answer(text: str) -> str:
    """Normalize QA answers for case- and accent-insensitive comparison."""
    normalized = unicodedata.normalize("NFKD", text.strip())
    without_marks = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return without_marks.upper()


def parse_points_field(points: str) -> tuple[tuple[int, int], ...]:
    """Parse comma-separated frame points into ordered [start, end] pairs."""
    values = [int(part.strip()) for part in points.split(",") if part.strip()]
    if len(values) % 2 != 0:
        raise ValueError(f"points must contain an even number of integers, got {values!r}.")
    return tuple((values[index], values[index + 1]) for index in range(0, len(values), 2))


def load_groundtruth_csv(path: Path | str) -> list[GroundTruthQuery]:
    """Load organizer-style ground truth: id,type,scene_id,video_id,points,answer."""
    csv_path = Path(path)
    queries: list[GroundTruthQuery] = []

    with csv_path.open("r", encoding="utf-8", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        required = {"id", "type", "scene_id", "video_id", "points"}
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            raise ValueError(
                f"Invalid ground-truth schema in {csv_path}. Required columns: {sorted(required)}"
            )

        for row in reader:
            scene_id = row["scene_id"].strip()
            video_id = row["video_id"].strip()
            media_item_name = f"{scene_id}_{video_id}" if "_" not in video_id else video_id
            if "_" not in media_item_name:
                media_item_name = f"{scene_id}_{video_id}"

            queries.append(
                GroundTruthQuery(
                    query_id=int(row["id"]),
                    task_type=row["type"].strip().upper(),
                    media_item_name=media_item_name,
                    frame_ranges=parse_points_field(row["points"]),
                    answer=(row.get("answer") or "").strip() or None,
                )
            )

    return queries


def frame_matches_range(frame_id: int, start: int, end: int, *, tolerance: int = 0) -> bool:
    low = min(start, end) - tolerance
    high = max(start, end) + tolerance
    return low <= frame_id <= high


def location_r_score(
    *,
    video_id: str,
    frame_id: int,
    ground_truth: GroundTruthQuery,
    tolerance: int = 0,
) -> float:
    """Return 1.0 when video and frame fall inside any accepted ground-truth range."""
    if video_id != ground_truth.media_item_name:
        return 0.0

    for start, end in ground_truth.frame_ranges:
        if frame_matches_range(frame_id, start, end, tolerance=tolerance):
            return 1.0
    return 0.0


def kis_result_r_score(
    result: dict[str, Any],
    ground_truth: GroundTruthQuery,
    *,
    tolerance: int = 0,
) -> float:
    return location_r_score(
        video_id=str(result.get("video_id", "")),
        frame_id=int(result.get("frame_id", -1)),
        ground_truth=ground_truth,
        tolerance=tolerance,
    )


def vqa_result_r_score(
    result: dict[str, Any],
    ground_truth: GroundTruthQuery,
    *,
    tolerance: int = 0,
) -> float:
    """Binary score: correct video, frame in range, and matching answer."""
    location_score = location_r_score(
        video_id=str(result.get("video_id", "")),
        frame_id=int(result.get("frame_id", -1)),
        ground_truth=ground_truth,
        tolerance=tolerance,
    )
    if location_score == 0.0 or not ground_truth.answer:
        return 0.0

    submitted = normalize_answer(str(result.get("answer", "")))
    expected = normalize_answer(ground_truth.answer)
    return 1.0 if submitted == expected else 0.0


def trake_result_r_score(
    result: dict[str, Any],
    ground_truth: GroundTruthQuery,
    *,
    tolerance: int = 0,
) -> float:
    """Partial credit: (1/N) * matched moments with positional frame alignment."""
    if str(result.get("video_id", "")) != ground_truth.media_item_name:
        return 0.0

    if not ground_truth.frame_ranges:
        return 0.0

    frames_raw = result.get("event_frames", result.get("frames", []))
    submitted_frames = [int(frame) for frame in frames_raw]
    event_count = len(ground_truth.frame_ranges)

    matched = 0
    for index, (start, end) in enumerate(ground_truth.frame_ranges):
        if index >= len(submitted_frames):
            break
        if frame_matches_range(submitted_frames[index], start, end, tolerance=tolerance):
            matched += 1

    return matched / event_count


def score_ranked_results(
    results: Sequence[dict[str, Any]],
    ground_truth: GroundTruthQuery,
    *,
    tolerance: int = 0,
) -> list[float]:
    task_type = ground_truth.task_type
    if task_type in {"KIS", "TKIS", "TEXTUAL_KIS"}:
        scorer = lambda item: kis_result_r_score(item, ground_truth, tolerance=tolerance)
    elif task_type in {"QA", "VQA"}:
        scorer = lambda item: vqa_result_r_score(item, ground_truth, tolerance=tolerance)
    elif task_type in {"TR", "TRAKE"}:
        scorer = lambda item: trake_result_r_score(item, ground_truth, tolerance=tolerance)
    else:
        raise ValueError(f"Unsupported task type: {ground_truth.task_type}")

    return [scorer(result) for result in results]


def compute_r_at_k(result_r_scores: Sequence[float], k: int) -> float:
    """Official R@k = best R-Score within the top-k ranked results."""
    bucket = result_r_scores[: max(int(k), 0)]
    return max(bucket) if bucket else 0.0


def compute_competition_query_score(
    result_r_scores: Sequence[float],
    k_values: Sequence[int] = DEFAULT_COMPETITION_K_VALUES,
) -> dict[str, Any]:
    r_at_k = {str(k): compute_r_at_k(result_r_scores, k) for k in k_values}
    final_score = sum(r_at_k.values()) / len(r_at_k) if r_at_k else 0.0
    return {
        "k_values": [int(k) for k in k_values],
        "r_at_k": r_at_k,
        "final_score": round(final_score, 6),
        "result_count": len(result_r_scores),
    }


def grade_query(
    results: Sequence[dict[str, Any]],
    ground_truth: GroundTruthQuery,
    *,
    tolerance: int = 0,
    k_values: Sequence[int] = DEFAULT_COMPETITION_K_VALUES,
) -> dict[str, Any]:
    per_result = score_ranked_results(results, ground_truth, tolerance=tolerance)
    competition = compute_competition_query_score(per_result, k_values)
    return {
        "query_id": ground_truth.query_id,
        "task_type": ground_truth.task_type,
        "media_item_name": ground_truth.media_item_name,
        "per_result_r_scores": per_result[:10],
        **competition,
    }


def grade_submission(
    ranked_results_by_query_id: dict[int | str, Sequence[dict[str, Any]]],
    ground_truth_queries: Sequence[GroundTruthQuery],
    *,
    tolerance: int = 0,
    k_values: Sequence[int] = DEFAULT_COMPETITION_K_VALUES,
) -> dict[str, Any]:
    query_reports: list[dict[str, Any]] = []
    for ground_truth in ground_truth_queries:
        results = ranked_results_by_query_id.get(ground_truth.query_id)
        if results is None:
            results = ranked_results_by_query_id.get(str(ground_truth.query_id), [])
        query_reports.append(
            grade_query(results, ground_truth, tolerance=tolerance, k_values=k_values)
        )

    if not query_reports:
        return {
            "query_count": 0,
            "mean_final_score": 0.0,
            "total_points": 0.0,
            "queries": [],
        }

    mean_final = sum(report["final_score"] for report in query_reports) / len(query_reports)
    return {
        "query_count": len(query_reports),
        "mean_final_score": round(mean_final, 6),
        "total_points": round(sum(report["final_score"] for report in query_reports), 6),
        "queries": query_reports,
    }
