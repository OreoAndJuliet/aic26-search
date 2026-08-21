"""Run full KIS/VQA/TRAKE batches with timing and grading summaries."""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from app.bootstrap import initialize_engines
from app.core.config import settings
from app.features.search.service import run_search
from app.features.submission.adapter import search_response_to_grading_results
from app.services.aic_grading import grade_submission
from app.utils.latency_stats import summarize_latencies


@dataclass
class QueryTiming:
    query_id: int
    task_type: str
    total_time_ms: float
    retrieval_time_ms: float
    translation_time_ms: float
    vlm_time_ms: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "query_id": self.query_id,
            "task_type": self.task_type,
            "total_time_ms": self.total_time_ms,
            "retrieval_time_ms": self.retrieval_time_ms,
            "translation_time_ms": self.translation_time_ms,
            "vlm_time_ms": self.vlm_time_ms,
        }


@dataclass
class CompetitionBatchResult:
    grading_results: dict[int, list[dict[str, Any]]] = field(default_factory=dict)
    responses: list[dict[str, Any]] = field(default_factory=list)
    timings: list[QueryTiming] = field(default_factory=list)
    total_elapsed_ms: float = 0.0

    def latency_summary(self) -> dict[str, Any]:
        totals = [timing.total_time_ms for timing in self.timings]
        summary = summarize_latencies(totals)
        sla_ms = settings.LATENCY_SLA_MS
        violations = sum(1 for value in totals if value > sla_ms)
        return {
            **summary,
            "sla_ms": sla_ms,
            "sla_violations": float(violations),
            "p95_within_sla": summary["p95_ms"] <= sla_ms,
        }


async def run_competition_batch(queries: list[dict[str, Any]]) -> CompetitionBatchResult:
    """Execute all competition queries through the unified search service."""
    initialize_engines()
    started_at = time.perf_counter()

    result = CompetitionBatchResult()
    for item in queries:
        task_type = str(item["type"]).upper()
        if task_type in {"TR", "TRAKE"}:
            response = await run_search(
                task_type="TRAKE",
                query=item["query"] or " | ".join(item["events"]),
                question=None,
                top_k=int(item["top_k"]),
                events=item["events"] or None,
                top_k_per_event=int(item["top_k_per_event"]),
                request_id=f"mock-{item['id']}",
            )
        else:
            api_type = "VQA" if task_type in {"QA", "VQA"} else "KIS"
            response = await run_search(
                task_type=api_type,
                query=item["query"],
                question=item.get("question"),
                top_k=int(item["top_k"]),
                request_id=f"mock-{item['id']}",
            )

        result.responses.append(response)
        result.grading_results[int(item["id"])] = search_response_to_grading_results(response)
        result.timings.append(
            QueryTiming(
                query_id=int(item["id"]),
                task_type=task_type,
                total_time_ms=float(response.get("total_time_ms", 0.0)),
                retrieval_time_ms=float(response.get("retrieval_time_ms", 0.0)),
                translation_time_ms=float(response.get("translation_time_ms", 0.0)),
                vlm_time_ms=float(response.get("vlm_time_ms", 0.0)),
            )
        )

    result.total_elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
    return result


def summarize_grading_by_task_type(grading_report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    buckets: dict[str, list[float]] = defaultdict(list)
    for query_report in grading_report.get("queries", []):
        buckets[str(query_report["task_type"])].append(float(query_report["final_score"]))

    summary: dict[str, dict[str, Any]] = {}
    for task_type, scores in sorted(buckets.items()):
        summary[task_type] = {
            "query_count": len(scores),
            "mean_final_score": round(sum(scores) / len(scores), 6) if scores else 0.0,
        }
    return summary


def build_competition_report(
    *,
    batch: CompetitionBatchResult,
    grading_report: dict[str, Any],
    budget_hours: float,
    sample_fraction: float,
    query_count_total: int,
) -> dict[str, Any]:
    budget_ms = round(budget_hours * 3600 * 1000, 2)
    latency = batch.latency_summary()
    return {
        "status": "ok",
        "query_count": len(batch.timings),
        "query_count_total": query_count_total,
        "sample_fraction": sample_fraction,
        "grading": {
            "mean_final_score": grading_report.get("mean_final_score", 0.0),
            "total_points": grading_report.get("total_points", 0.0),
            "by_task_type": summarize_grading_by_task_type(grading_report),
            "queries": grading_report.get("queries", []),
        },
        "timing": {
            "total_elapsed_ms": batch.total_elapsed_ms,
            "budget_hours": budget_hours,
            "budget_ms": budget_ms,
            "within_budget": batch.total_elapsed_ms <= budget_ms,
            **latency,
            "slowest_queries": sorted(
                (timing.to_dict() for timing in batch.timings),
                key=lambda item: item["total_time_ms"],
                reverse=True,
            )[:5],
        },
    }


def grade_batch_results(
    batch: CompetitionBatchResult,
    ground_truth_path: str,
    *,
    tolerance: int = 0,
) -> dict[str, Any]:
    from pathlib import Path

    from app.services.aic_grading import load_groundtruth_csv

    ground_truth = load_groundtruth_csv(Path(ground_truth_path))
    return grade_submission(batch.grading_results, ground_truth, tolerance=tolerance)
