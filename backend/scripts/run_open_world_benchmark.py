"""Official Open-World Codabench Evaluation Runner and Submission Packager for AIC 2026."""

import os
import sys

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

import json
import time
import zipfile
import asyncio
from pathlib import Path
from dataclasses import dataclass, field, asdict

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

@dataclass
class QueryResult:
    query_id: str
    task_type: str
    category: str
    query_text: str
    expected_video_id: str
    expected_timestamp: float
    rank_found: int
    r_score: float
    official_query_score: float
    latency_ms: float
    status: str
    matched_video_id: str = ""
    matched_frame_id: int = 0
    matched_timestamp: float = 0.0
    predicted_answer: str = ""

@dataclass
class CodabenchSummary:
    benchmark_name: str
    total_queries: int
    evaluated_at: str
    kis_count: int = 0
    vqa_count: int = 0
    trake_count: int = 0
    official_mean_score: float = 0.0
    kis_mean_score: float = 0.0
    r_at_1: float = 0.0
    r_at_5: float = 0.0
    r_at_20: float = 0.0
    r_at_50: float = 0.0
    r_at_100: float = 0.0
    vqa_accuracy: float = 0.0
    trake_accuracy: float = 0.0
    mean_latency_ms: float = 0.0
    results: list[QueryResult] = field(default_factory=list)


async def run_open_world_benchmark(dataset_path: str = "data/open_world_codabench_benchmark.json"):
    from app.bootstrap import initialize_engines
    initialize_engines()
    from app.features.search.service import run_search

    p = REPO_ROOT / dataset_path
    if not p.is_file():
        raise FileNotFoundError(f"Open-world benchmark file not found: {p}")

    data = json.loads(p.read_text(encoding="utf-8"))
    queries = data.get("queries", [])
    bench_name = data.get("benchmark_name", "Open-World Codabench Benchmark")

    print("\n" + "=" * 70)
    print("     AIC 2026 OPEN-WORLD CODABENCH EVALUATION BENCHMARK        ")
    print("=" * 70)
    print(f"  Benchmark Name:  {bench_name}")
    print(f"  Total Queries:   {len(queries)}")
    print(f"  Metric:          Codabench Official Mean of Top-k Max R-Score")
    print("-" * 70)

    results: list[QueryResult] = []
    latencies: list[float] = []

    kis_scores: list[float] = []
    kis_r1, kis_r5, kis_r20, kis_r50, kis_r100 = 0, 0, 0, 0, 0
    kis_total = 0

    vqa_hits, vqa_total = 0, 0
    trake_hits, trake_total = 0, 0

    for idx, q in enumerate(queries, start=1):
        qid = q.get("query_id", f"Q_{idx}")
        ttype = q.get("task_type", "KIS").upper()
        cat = q.get("category", "general")
        qtext = q.get("query", "")
        question = q.get("question", "")
        events = q.get("events", [])
        exp_vid = q.get("expected_video_id", "")
        exp_ts = float(q.get("expected_timestamp", 0.0))
        acceptable_vids = set(q.get("acceptable_video_ids", [exp_vid]))

        t0 = time.perf_counter()

        if ttype == "TRAKE":
            trake_total += 1
            res = await run_search(task_type="TRAKE", query="", question=None, top_k=10, events=events)
            lat = (time.perf_counter() - t0) * 1000
            latencies.append(lat)

            items = res.get("results", [])
            matched_vid = items[0].get("video_id", "") if items else ""
            is_monotonic = True
            if items and "trajectory" in items[0]:
                ts_list = [t.get("timestamp", 0.0) for t in items[0]["trajectory"]]
                is_monotonic = all(ts_list[i] < ts_list[i+1] for i in range(len(ts_list)-1))

            is_hit = (matched_vid in acceptable_vids or matched_vid == exp_vid) and is_monotonic
            score = 1.0 if is_hit else 0.0
            if is_hit:
                trake_hits += 1

            status = "[ALIGNED]" if is_hit else "[MISALIGNED]"
            results.append(QueryResult(
                query_id=qid,
                task_type=ttype,
                category=cat,
                query_text=" -> ".join(events),
                expected_video_id=exp_vid,
                expected_timestamp=0.0,
                rank_found=1 if is_hit else -1,
                r_score=score,
                official_query_score=score,
                latency_ms=round(lat, 2),
                status=status,
                matched_video_id=matched_vid
            ))
            print(f"[{idx:02d}/{len(queries):02d}] [TRAKE] {qid:<12} Exp: {exp_vid:<10} Matched: {matched_vid:<10} {status:<12} Lat: {lat:.1f}ms")

        elif ttype == "VQA":
            vqa_total += 1
            exp_ans = str(q.get("expected_answer", "")).lower().strip()
            acceptable_ans = [a.lower().strip() for a in q.get("acceptable_answers", [exp_ans])]

            res = await run_search(task_type="VQA", query=qtext, question=question, top_k=5)
            lat = (time.perf_counter() - t0) * 1000
            latencies.append(lat)

            items = res.get("results", [])
            pred_ans = ""
            if items:
                pred_ans = str(items[0].get("answer", "")).lower().strip()

            is_correct = any(a in pred_ans or pred_ans in a for a in acceptable_ans if a)
            score = 1.0 if is_correct else 0.0
            if is_correct:
                vqa_hits += 1

            status = "[CORRECT]" if is_correct else "[MISMATCH]"
            results.append(QueryResult(
                query_id=qid,
                task_type=ttype,
                category=cat,
                query_text=f"{qtext} | {question}",
                expected_video_id=exp_vid,
                expected_timestamp=0.0,
                rank_found=1 if is_correct else -1,
                r_score=score,
                official_query_score=score,
                latency_ms=round(lat, 2),
                status=status,
                predicted_answer=pred_ans
            ))
            print(f"[{idx:02d}/{len(queries):02d}] [VQA]   {qid:<12} Exp: {exp_ans:<10} Pred: {pred_ans:<15} {status:<12} Lat: {lat:.1f}ms")

        else: # KIS
            kis_total += 1
            res = await run_search(task_type="KIS", query=qtext, question=None, top_k=100)
            lat = (time.perf_counter() - t0) * 1000
            latencies.append(lat)

            items = res.get("results", [])
            rank_found = -1
            best_rscore = 0.0
            matched_vid = ""
            matched_fid = 0
            matched_ts = 0.0

            for r_idx, it in enumerate(items, start=1):
                vid = str(it.get("video_id", ""))
                ts = float(it.get("timestamp", 0.0))
                fid = int(it.get("frame_id", 0))

                if vid in acceptable_vids and abs(ts - exp_ts) <= 30.0:
                    if rank_found == -1:
                        rank_found = r_idx
                        matched_vid = vid
                        matched_fid = fid
                        matched_ts = ts
                        best_rscore = max(0.0, 1.0 - (abs(ts - exp_ts) / 60.0))

            q_official = 0.0
            if rank_found > 0:
                if rank_found <= 1:
                    kis_r1 += 1
                if rank_found <= 5:
                    kis_r5 += 1
                if rank_found <= 20:
                    kis_r20 += 1
                if rank_found <= 50:
                    kis_r50 += 1
                if rank_found <= 100:
                    kis_r100 += 1

                for k in (1, 5, 20, 50, 100):
                    if rank_found <= k:
                        q_official += best_rscore
                q_official /= 5.0
                kis_scores.append(q_official)
                status = f"[HIT #{rank_found}]"
            else:
                kis_scores.append(0.0)
                status = "[MISS]"

            results.append(QueryResult(
                query_id=qid,
                task_type=ttype,
                category=cat,
                query_text=qtext,
                expected_video_id=exp_vid,
                expected_timestamp=exp_ts,
                rank_found=rank_found,
                r_score=best_rscore,
                official_query_score=q_official,
                latency_ms=round(lat, 2),
                status=status,
                matched_video_id=matched_vid,
                matched_frame_id=matched_fid,
                matched_timestamp=matched_ts
            ))
            print(f"[{idx:02d}/{len(queries):02d}] [KIS]   {qid:<12} Exp: {exp_vid:<10} Score: {q_official:>6.4f} {status:<12} Lat: {lat:.1f}ms")

    # Aggregate Metrics
    kis_mean = sum(kis_scores) / max(1, kis_total) if kis_total else 0.0
    vqa_acc = (vqa_hits / max(1, vqa_total)) * 100.0 if vqa_total else 0.0
    trake_acc = (trake_hits / max(1, trake_total)) * 100.0 if trake_total else 0.0

    all_scores = [r.official_query_score for r in results]
    overall_mean = sum(all_scores) / max(1, len(all_scores))
    mean_lat = sum(latencies) / max(1, len(latencies))

    summary = CodabenchSummary(
        benchmark_name=bench_name,
        total_queries=len(queries),
        evaluated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        kis_count=kis_total,
        vqa_count=vqa_total,
        trake_count=trake_total,
        official_mean_score=round(overall_mean, 6),
        kis_mean_score=round(kis_mean, 6),
        r_at_1=round((kis_r1 / max(1, kis_total)) * 100.0, 2),
        r_at_5=round((kis_r5 / max(1, kis_total)) * 100.0, 2),
        r_at_20=round((kis_r20 / max(1, kis_total)) * 100.0, 2),
        r_at_50=round((kis_r50 / max(1, kis_total)) * 100.0, 2),
        r_at_100=round((kis_r100 / max(1, kis_total)) * 100.0, 2),
        vqa_accuracy=round(vqa_acc, 2),
        trake_accuracy=round(trake_acc, 2),
        mean_latency_ms=round(mean_lat, 2),
        results=results
    )

    # 4. Package Official Codabench Submission ZIP
    sub_dir = REPO_ROOT / "data" / "submissions"
    sub_dir.mkdir(parents=True, exist_ok=True)
    out_json = sub_dir / "submission_results.json"
    out_csv = sub_dir / "submission_results.csv"
    out_zip = sub_dir / "codabench_open_world_submission.zip"

    # Export JSON
    out_json.write_text(json.dumps(asdict(summary), indent=2, ensure_ascii=False), encoding="utf-8")

    # Export CSV for Codabench
    with out_csv.open("w", encoding="utf-8") as f:
        f.write("query_id,task_type,rank_found,r_score,official_score,latency_ms,status,video_id,frame_id,timestamp,predicted_answer\n")
        for r in results:
            f.write(f"{r.query_id},{r.task_type},{r.rank_found},{r.r_score:.4f},{r.official_query_score:.4f},{r.latency_ms:.2f},{r.status},{r.matched_video_id},{r.matched_frame_id},{r.matched_timestamp:.2f},\"{r.predicted_answer}\"\n")

    # Create ZIP
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(out_json, arcname="results.json")
        zf.write(out_csv, arcname="results.csv")

    print("\n" + "=" * 70)
    print("            CODABENCH BENCHMARK RESULTS SUMMARY                   ")
    print("=" * 70)
    print(f"  🏆 Codabench Official Mean Score : {summary.official_mean_score:.6f}")
    print(f"  🎯 KIS Mean R-Score (10 Queries) : {summary.kis_mean_score:.4f}")
    print(f"     + R@1 (Top-1 Exact Hit)       : {summary.r_at_1:.1f}%")
    print(f"     + R@5 (Top-5 Recall)          : {summary.r_at_5:.1f}%")
    print(f"     + R@20 (Top-20 Recall)        : {summary.r_at_20:.1f}%")
    print(f"     + R@100 (Hit Rate)            : {summary.r_at_100:.1f}%")
    print(f"  💬 VQA Accuracy (5 Queries)      : {summary.vqa_accuracy:.1f}% ({vqa_hits}/{vqa_total})")
    print(f"  ⏱️  TRAKE Alignment (3 Queries)   : {summary.trake_accuracy:.1f}% ({trake_hits}/{trake_total})")
    print(f"  ⚡ Mean Latency per Query        : {summary.mean_latency_ms:.2f} ms")
    print("-" * 70)
    print(f"  📦 Codabench Submission ZIP Exported: {out_zip}")
    print("=" * 70 + "\n")

    return summary


if __name__ == "__main__":
    asyncio.run(run_open_world_benchmark())
