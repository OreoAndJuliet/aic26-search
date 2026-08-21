"""Build competition submission JSON/CSV from a query batch."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.features.competition.batch import grade_batch_results, run_competition_batch
from app.features.competition.queries import load_query_batch
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run queries and build official AIC submission JSON + CSV/ZIP exports."
    )
    parser.add_argument("--queries", required=True, help="CSV with id,type,query,question,events")
    parser.add_argument("--team-session-id", default="local-dev-session")
    parser.add_argument("--output-json", type=Path, default=Path("submission/submission.json"))
    parser.add_argument(
        "--output-csv-dir",
        type=Path,
        default=Path("submission/submission"),
        help="Folder for per-query CSV files (Codabench layout)",
    )
    parser.add_argument(
        "--output-zip",
        type=Path,
        default=Path("submission/codabench.zip"),
        help="Codabench-ready ZIP with submission/ folder inside",
    )
    parser.add_argument("--groundtruth", type=Path, help="Optional groundtruth.csv for local grading")
    parser.add_argument("--skip-csv", action="store_true")
    args = parser.parse_args(argv)

    try:
        queries = load_query_batch(Path(args.queries))
        batch = asyncio.run(run_competition_batch(queries))
        answer_sets = [
            build_answer_set(
                item["type"],
                response.get("results", []),
                trake_meta=response.get("trake"),
            )
            for item, response in zip(queries, batch.responses, strict=True)
        ]
        payload = build_submission_payload(args.team_session_id, answer_sets)

        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")

        csv_exports: list[str] = []
        zip_entries: list[tuple[str, list[list[str | int]], str]] = []
        if not args.skip_csv:
            args.output_csv_dir.mkdir(parents=True, exist_ok=True)
            for item, response in zip(queries, batch.responses, strict=True):
                rows = results_to_csv_rows(
                    item["type"],
                    response.get("results", []),
                    trake_meta=response.get("trake"),
                )
                csv_name = codabench_csv_name(item["id"], item["type"])
                csv_path = args.output_csv_dir / csv_name
                write_submission_csv(csv_path, rows, task_type=item["type"])
                csv_exports.append(str(csv_path))
                zip_entries.append((csv_name, rows, item["type"]))

            build_codabench_zip(args.output_zip, zip_entries)

        report: dict[str, Any] = {
            "status": "ok",
            "query_count": len(queries),
            "submission_json": str(args.output_json),
            "csv_exports": csv_exports,
            "codabench_zip": str(args.output_zip) if not args.skip_csv else None,
            "grading_results_path": str(args.output_json.with_name("grading_results.json")),
        }

        grading_path = args.output_json.with_name("grading_results.json")
        grading_path.write_text(
            json.dumps(
                {str(key): value for key, value in batch.grading_results.items()},
                indent=2,
            ),
            encoding="utf-8",
        )

        if args.groundtruth:
            report["grading"] = grade_batch_results(batch, str(args.groundtruth))

        print(json.dumps(report, indent=2))
        return 0
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        print(json.dumps({"status": "failed", "error": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
