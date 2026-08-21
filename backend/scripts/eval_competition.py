"""Grade ranked retrieval results against official AIC ground-truth labels."""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.bootstrap import initialize_engines
from app.features.competition.batch import (
    build_competition_report,
    grade_batch_results,
    run_competition_batch,
)
from app.features.competition.queries import (
    load_query_batch,
    load_query_text_map,
    merge_queries_with_groundtruth_types,
    sample_queries,
)
from app.services.aic_grading import grade_submission, load_groundtruth_csv
from app.services.kis_engine import kis_engine
from app.services.translator import translator


async def _run_live_kis(
    groundtruth_path: Path,
    queries_path: Path,
    *,
    top_k: int,
    tolerance: int,
) -> dict:
    ground_truth = load_groundtruth_csv(groundtruth_path)
    query_texts = load_query_text_map(queries_path)
    initialize_engines()

    ranked_results: dict[int, list[dict]] = {}
    for item in ground_truth:
        if item.task_type not in {"KIS", "TKIS", "TEXTUAL_KIS"}:
            ranked_results[item.query_id] = []
            continue

        query_text = query_texts.get(item.query_id)
        if not query_text:
            raise ValueError(f"Missing query text for ground-truth id={item.query_id}")

        from app.features.search.retrieval import run_kis_retrieval
        translation = await translator.translate_async(query_text)
        results, _metrics = run_kis_retrieval(translation.text, top_k, raw_query=query_text)
        ranked_results[item.query_id] = results

    return grade_submission(ranked_results, ground_truth, tolerance=tolerance)


def _load_results_file(path: Path) -> dict[int | str, list[dict]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and "queries" in payload:
        payload = payload["queries"]
    if not isinstance(payload, dict):
        raise TypeError("Results file must be a JSON object keyed by query id.")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Grade ranked results using official AIC Mean of Top-k R-Score."
    )
    parser.add_argument(
        "--groundtruth",
        required=True,
        help="Path to groundtruth.csv (id,type,scene_id,video_id,points,answer)",
    )
    parser.add_argument(
        "--results",
        help="JSON file mapping query_id -> ranked result list.",
    )
    parser.add_argument(
        "--queries",
        help="CSV file with id,query text. Used with live search when --results is omitted.",
    )
    parser.add_argument(
        "--full-batch",
        action="store_true",
        help="Run KIS/VQA/TRAKE through unified search when --queries includes type/events.",
    )
    parser.add_argument(
        "--sample-fraction",
        type=float,
        default=1.0,
        help="Optional fraction of --queries rows to execute before grading.",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--top-k", type=int, default=100, help="Live KIS top_k")
    parser.add_argument(
        "--tolerance",
        type=int,
        default=0,
        help="Accepted frame-index tolerance around each ground-truth range",
    )
    args = parser.parse_args()

    groundtruth_path = Path(args.groundtruth)
    try:
        if args.results:
            queries = load_groundtruth_csv(groundtruth_path)
            ranked_results = _load_results_file(Path(args.results))
            report = grade_submission(
                ranked_results,
                queries,
                tolerance=args.tolerance,
            )
            print(json.dumps({"status": "ok", **report}, indent=2))
            return 0

        if not args.queries:
            raise ValueError("Provide either --results or --queries for live grading.")

        if args.full_batch or _queries_include_task_types(Path(args.queries)):
            all_queries = load_query_batch(Path(args.queries))
            ground_truth = load_groundtruth_csv(groundtruth_path)
            all_queries = merge_queries_with_groundtruth_types(all_queries, ground_truth)
            selected = sample_queries(
                all_queries,
                fraction=args.sample_fraction,
                seed=args.seed,
            )
            batch = asyncio.run(run_competition_batch(selected))
            grading_report = grade_batch_results(
                batch,
                str(groundtruth_path),
                tolerance=args.tolerance,
            )
            report = build_competition_report(
                batch=batch,
                grading_report=grading_report,
                budget_hours=3.0,
                sample_fraction=args.sample_fraction,
                query_count_total=len(all_queries),
            )
            print(json.dumps(report, indent=2))
            return 0

        report = asyncio.run(
            _run_live_kis(
                groundtruth_path,
                Path(args.queries),
                top_k=args.top_k,
                tolerance=args.tolerance,
            )
        )
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        print(json.dumps({"status": "failed", "error": str(exc)}))
        return 1

    print(json.dumps({"status": "ok", **report}, indent=2))
    return 0


def _queries_include_task_types(path: Path) -> bool:
    with path.open("r", encoding="utf-8", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        if not reader.fieldnames or "type" not in reader.fieldnames:
            return False
        for row in reader:
            task_type = (row.get("type") or "").strip().upper()
            if task_type and task_type != "KIS":
                return True
            if (row.get("events") or "").strip():
                return True
    return False


if __name__ == "__main__":
    sys.exit(main())
