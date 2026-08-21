"""Live TRAKE multi-event sequence alignment test script."""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.bootstrap import initialize_engines
from app.features.search.service import run_search
from app.services.trake_engine import trake_engine


async def test_trake_scenarios():
    print("=================================================================")
    print("           TRAKE MULTI-EVENT SEQUENCE RETRIEVAL TEST             ")
    print("=================================================================")
    print("Warming up search engines and loading FAISS index...")
    initialize_engines()
    print("Engines warmed up successfully!")

    test_queries = [
        {
            "name": "Scenario 1: Indoor Activity Sequence (3 events)",
            "events": [
                "a person walking into room",
                "a person sitting down at a desk",
                "a person standing up and leaving",
            ],
            "max_gap": 300.0,
        },
        {
            "name": "Scenario 2: Traffic & Street Motion (2 events)",
            "events": [
                "cars driving on the road",
                "a motorbike turning at the intersection",
            ],
            "max_gap": 180.0,
        },
        {
            "name": "Scenario 3: Vietnamese Query with Automatic Translation",
            "events": [
                "người đi bộ trên đường",
                "xe máy dừng lại",
            ],
            "max_gap": 240.0,
        },
    ]

    for scenario in test_queries:
        print(f"\n>>> Running {scenario['name']}")
        print(f"    Input Events: {' -> '.join(scenario['events'])}")
        
        t0 = time.perf_counter()
        resp = await run_search(
            task_type="TRAKE",
            query="",
            question=None,
            top_k=20,
            events=scenario["events"],
            top_k_per_event=50,
            max_gap_seconds=scenario["max_gap"],
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000

        results = resp.get("results", [])
        trake_meta = resp.get("trake", {})

        print(f"    Completed in: {elapsed_ms:.1f}ms (Translation: {resp.get('translation_time_ms', 0):.1f}ms, Retrieval: {resp.get('retrieval_time_ms', 0):.1f}ms)")
        print(f"    Aligned Video: {trake_meta.get('video_id', 'None')}")
        print(f"    Alignment Score: {trake_meta.get('alignment_score', 0.0):.4f}")
        print(f"    Event Frames: {trake_meta.get('event_frames', [])}")
        print(f"    Temporal Gaps (s): {trake_meta.get('temporal_gaps', [])}")

        if results:
            print("    Trajectory Details:")
            prev_ts = None
            is_monotonic = True
            for r in results:
                evt_idx = r.get("event_index")
                evt_txt = r.get("event_text")
                vid = r.get("video_id")
                fid = r.get("frame_id")
                kfid = r.get("keyframe_id")
                ts = r.get("timestamp", 0.0)
                score = r.get("score", 0.0)
                
                if prev_ts is not None and ts < prev_ts:
                    is_monotonic = False
                prev_ts = ts
                
                print(f"      [Event #{evt_idx}] Frame {fid} (kf={kfid}) at {ts:.2f}s | Score={score:.4f} | {evt_txt[:40]}")
            
            print(f"    Temporal Monotonicity: {'PASS (t0 <= t1 <= t2)' if is_monotonic else 'FAIL'}")
            print(f"    Codabench Submission Row: {trake_meta.get('video_id')}, {', '.join(str(f) for f in trake_meta.get('event_frames', []))}")
        else:
            print(f"    No trajectory found: {trake_meta.get('error')}")

    print("\n=================================================================")
    print("                    TRAKE TEST COMPLETE                          ")
    print("=================================================================")


if __name__ == "__main__":
    asyncio.run(test_trake_scenarios())
