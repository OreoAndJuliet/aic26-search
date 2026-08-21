"""Headless CLI Runner for AIC 2026 Mock Contest Evaluation Harness."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from dataclasses import asdict

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

# Ensure project root is in sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.features.submission.evaluation_engine import (
    evaluate_benchmark,
    package_codabench_submission,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="AIC 2026 Mock Contest Evaluation Runner")
    parser.add_argument("--suite", choices=["all", "kis", "vqa", "trake"], default="all", help="Task suite to run")
    parser.add_argument("--topk", type=int, default=10, help="Top-K candidates per query")
    parser.add_argument("--tolerance", type=float, default=30.0, help="Temporal tolerance window in seconds")
    parser.add_argument("--base-url", default="http://localhost:8000", help="FastAPI backend URL")
    parser.add_argument("--export-zip", action="store_true", help="Generate Codabench submission zip")
    parser.add_argument("--output-json", default="data/evaluation_results.json", help="Path to write JSON results")
    args = parser.parse_args()

    print("=================================================================")
    print("      AIC 2026 OFFICIAL MOCK CONTEST EVALUATION HARNESS          ")
    print("=================================================================")
    print(f"  Suite:       {args.suite.upper()}")
    print(f"  Top-K:       {args.topk}")
    print(f"  Tolerance:   ±{args.tolerance}s")
    print(f"  Target:      {args.base_url}")
    print("-----------------------------------------------------------------")

    gt_path = REPO_ROOT / "data" / "mock_contest_ground_truth.json"
    out_json_path = Path(args.output_json) if Path(args.output_json).is_absolute() else (REPO_ROOT / args.output_json)

    try:
        summary = evaluate_benchmark(
            ground_truth_path=gt_path,
            base_url=args.base_url,
            task_filter=args.suite,
            top_k=args.topk,
            tolerance_seconds=args.tolerance,
        )
    except Exception as exc:
        print(f"ERROR: Evaluation failed: {exc}", file=sys.stderr)
        sys.exit(1)

    print("\n--- INDIVIDUAL QUERY RESULTS ---")
    for r in summary.results:
        status = "[HIT]" if (r.top1_hit or r.vqa_correct or r.trake_monotonic) else "[MISS]"
        extra = ""
        if r.task_type == "KIS":
            extra = f"Rank={r.rank_found} ({r.matched_video_id}_{r.matched_frame_id})" if r.top10_hit else "Not in Top-10"
        elif r.task_type == "VQA":
            extra = f"Ans='{r.vqa_answer}' ({r.vqa_source})"
        elif r.task_type == "TRAKE":
            extra = f"Monotonic={r.trake_monotonic} ({r.trake_submission})"

        print(f"  {status} {r.query_id:<8} [{r.task_type:<5}] {r.latency_ms:>7.1f}ms | OfficialScore={r.official_query_score:.4f} | {r.query_text[:35]:<35} | {extra}")

    print("\n=================================================================")
    print("         OFFICIAL CODABENCH SCORE (Mean-of-Top-k-max-R@k)        ")
    print("=================================================================")
    print(f"  *** OFFICIAL MEAN SCORE:          {summary.official_mean_score:.6f} ***")
    print(f"  R@1  (GT in top-1):               {summary.r_at_1:.1f}%")
    print(f"  R@5  (GT in top-5):               {summary.r_at_5:.1f}%")
    print(f"  R@20 (GT in top-20):              {summary.r_at_20:.1f}%")
    print(f"  R@50 (GT in top-50):              {summary.r_at_50:.1f}%")
    print(f"  R@100 (GT in top-100):            {summary.r_at_100:.1f}%")
    print("-----------------------------------------------------------------")
    print("         INTERNAL QUALITY METRICS (not competition score)         ")
    print("-----------------------------------------------------------------")
    print(f"  Total Queries Evaluated:    {summary.total_queries}")
    print(f"  KIS Top-1 Accuracy:         {summary.top1_accuracy:.1f}%")
    print(f"  KIS Recall@5 (R@5):         {summary.recall_at_5:.1f}%")
    print(f"  KIS Recall@10 (R@10):       {summary.recall_at_10:.1f}%")
    print(f"  KIS Mean Reciprocal Rank:   {summary.mrr:.4f}")
    print(f"  VQA Accuracy:               {summary.vqa_accuracy:.1f}%")
    print(f"  TRAKE Sequence Accuracy:    {summary.trake_sequence_accuracy:.1f}%")
    print("-----------------------------------------------------------------")
    print(f"  Latency P50 (Median):       {summary.p50_latency_ms:.1f}ms")
    print(f"  Latency P95:                {summary.p95_latency_ms:.1f}ms")
    print(f"  Latency P99:                {summary.p99_latency_ms:.1f}ms")
    print(f"  Latency Mean:               {summary.mean_latency_ms:.1f}ms")
    print(f"  Latency Max:                {summary.max_latency_ms:.1f}ms")
    print(f"  SLA Compliance (<1000ms):   {summary.sla_compliance_pct:.1f}%")
    print("=================================================================")

    # Write JSON results
    out_json_path.parent.mkdir(parents=True, exist_ok=True)
    out_json_path.write_text(json.dumps(asdict(summary), indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  Results saved: {out_json_path.resolve()}")

    if args.export_zip:
        zip_path = package_codabench_submission(summary, output_dir=REPO_ROOT / "data" / "submissions")
        print(f"  Codabench Zip Created: {zip_path.resolve()}")


if __name__ == "__main__":
    main()
