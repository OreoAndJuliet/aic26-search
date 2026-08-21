"""Mock competition drill: batch search, grade, and 3-hour budget report."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.core.config import settings
from app.features.competition.batch import (
    build_competition_report,
    grade_batch_results,
    run_competition_batch,
)
from app.features.competition.queries import (
    load_query_batch,
    merge_queries_with_groundtruth_types,
    sample_queries,
)
from app.features.submission.adapter import (
    build_answer_set,
    build_submission_payload,
    results_to_csv_rows,
)
from app.features.submission.csv_export import (
    build_codabench_zip,
    codabench_csv_name,
    write_submission_csv,
)
from app.services.aic_grading import load_groundtruth_csv


def _write_artifacts(
    output_dir: Path,
    *,
    batch_result,
    grading_results: dict[int, list[dict[str, Any]]],
    answer_sets: list[dict],
    team_session_id: str,
    queries: list[dict[str, Any]],
    responses: list[dict[str, Any]],
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    grading_path = output_dir / "grading_results.json"
    submission_path = output_dir / "submission.json"

    grading_path.write_text(
        json.dumps({str(key): value for key, value in grading_results.items()}, indent=2),
        encoding="utf-8",
    )
    submission_path.write_text(
        json.dumps(build_submission_payload(team_session_id, answer_sets), indent=2),
        encoding="utf-8",
    )

    submission_dir = output_dir / "submission"
    zip_entries: list[tuple[str, list[list[str | int]], str]] = []
    for item, response in zip(queries, responses, strict=True):
        rows = results_to_csv_rows(
            item["type"],
            response.get("results", []),
            trake_meta=response.get("trake"),
        )
        csv_name = codabench_csv_name(item["id"], item["type"])
        write_submission_csv(submission_dir / csv_name, rows, task_type=item["type"])
        zip_entries.append((csv_name, rows, item["type"]))

    codabench_zip = output_dir / "codabench.zip"
    build_codabench_zip(codabench_zip, zip_entries)

    return {
        "grading_results": str(grading_path),
        "submission_json": str(submission_path),
        "submission_dir": str(submission_dir),
        "codabench_zip": str(codabench_zip),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run a mock AIC competition batch (KIS/VQA/TRAKE), grade, and check the 3h budget."
    )
    parser.add_argument("--queries", required=True, help="CSV with id,type,query,question,events")
    parser.add_argument(
        "--groundtruth",
        required=True,
        help="groundtruth.csv for official Mean of Top-k R-Score grading",
    )
    parser.add_argument(
        "--sample-fraction",
        type=float,
        default=float(getattr(settings, "MOCK_COMPETITION_SAMPLE_FRACTION", 0.5)),
        help="Fraction of queries to run (default 0.5 = 50%% mock drill)",
    )
    parser.add_argument("--seed", type=int, default=42, help="Deterministic sampling seed")
    parser.add_argument(
        "--budget-hours",
        type=float,
        default=float(getattr(settings, "MOCK_COMPETITION_BUDGET_HOURS", 3.0)),
        help="Mock competition time budget in hours (default 3)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Directory for grading_results.json, submission.json, report.json",
    )
    parser.add_argument("--team-session-id", default="mock-competition-session")
    parser.add_argument("--tolerance", type=int, default=0)
    parser.add_argument("--skip-submission-json", action="store_true")
    args = parser.parse_args(argv)

    try:
        all_queries = load_query_batch(Path(args.queries))
        ground_truth = load_groundtruth_csv(Path(args.groundtruth))
        all_queries = merge_queries_with_groundtruth_types(all_queries, ground_truth)
        selected = sample_queries(all_queries, fraction=args.sample_fraction, seed=args.seed)

        batch = asyncio.run(run_competition_batch(selected))
        grading_report = grade_batch_results(
            batch,
            args.groundtruth,
            tolerance=args.tolerance,
        )

        run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
        output_dir = args.output_dir or Path("submission") / f"mock_run_{run_id}"

        artifacts: dict[str, str] = {"grading_results": str(output_dir / "grading_results.json")}
        if not args.skip_submission_json:
            answer_sets = [
                build_answer_set(
                    item["type"],
                    response.get("results", []),
                    trake_meta=response.get("trake"),
                )
                for item, response in zip(selected, batch.responses, strict=True)
            ]
            artifacts = _write_artifacts(
                output_dir,
                batch_result=batch,
                grading_results=batch.grading_results,
                answer_sets=answer_sets,
                team_session_id=args.team_session_id,
                queries=selected,
                responses=batch.responses,
            )
        else:
            output_dir.mkdir(parents=True, exist_ok=True)
            artifacts["grading_results"] = str(output_dir / "grading_results.json")
            Path(artifacts["grading_results"]).write_text(
                json.dumps(
                    {str(key): value for key, value in batch.grading_results.items()},
                    indent=2,
                ),
                encoding="utf-8",
            )

        report = build_competition_report(
            batch=batch,
            grading_report=grading_report,
            budget_hours=args.budget_hours,
            sample_fraction=args.sample_fraction,
            query_count_total=len(all_queries),
        )
        report["run_id"] = run_id
        report["artifacts"] = artifacts

        report_path = output_dir / "report.json"
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        report["artifacts"]["report_json"] = str(report_path)

        print(json.dumps(report, indent=2))
        return 0 if report["timing"]["within_budget"] else 2
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        print(json.dumps({"status": "failed", "error": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
