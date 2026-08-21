"""Direct In-Process Search Runner for start.bat / start.ps1 CLI integration.

Allows executing KIS, VQA, and TRAKE searches directly with all multi-modal upgrades
(OCR boosting, speculative consensus judge, 0-token CV, landmark gazetteers) active.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Ensure UTF-8 output encoding on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.bootstrap import initialize_engines
from app.features.search.service import run_search


async def _run() -> None:
    parser = argparse.ArgumentParser(description="Direct Search with all upgrades active.")
    parser.add_argument("--mode", choices=["KIS", "VQA", "TRAKE"], default="KIS")
    parser.add_argument("--query", default="")
    parser.add_argument("--question", default="")
    parser.add_argument("--events", nargs="*", default=[])
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--json", action="store_true", help="Output raw JSON response")
    args = parser.parse_args()

    initialize_engines()

    events_list = args.events
    if not events_list and args.query and "|" in args.query and args.mode == "TRAKE":
        events_list = [e.strip() for e in args.query.split("|") if e.strip()]

    payload = {
        "task_type": args.mode,
        "query": args.query,
        "question": args.question or None,
        "events": events_list if events_list else None,
        "top_k": args.top_k,
    }

    response = await run_search(**payload)

    if args.json:
        print(json.dumps(response, indent=2, ensure_ascii=False))
        return

    results = response.get("results", [])
    mode = args.mode.upper()
    query = args.query

    print("\n" + "=" * 90)
    print(f"                       AIC 2026 DIRECT SEARCH REPORT ({mode})")
    print("=" * 90)
    print(f"Query:            {query}")
    if args.question:
        print(f"Question:         {args.question}")
    if events_list:
        print(f"Events:           {' -> '.join(events_list)}")
    print(f"Total Results:    {len(results)}")
    print("-" * 90)

    if mode == "VQA":
        print(f"{'Rank':<5} {'Video ID':<12} {'Frame':<8} {'Time(s)':<8} {'R-Score':<9} {'Answer':<20}")
        print("-" * 90)
        for idx, r in enumerate(results, start=1):
            vid = str(r.get("video_id", ""))
            fid = str(r.get("frame_id", ""))
            ts = f"{float(r.get('timestamp', 0.0)):.1f}s"
            rscore = f"{float(r.get('r_score', r.get('score', 0.0))):.4f}"
            ans = str(r.get("answer") or "N/A")[:20]
            print(f"#{idx:<4} {vid:<12} {fid:<8} {ts:<8} {rscore:<9} {ans:<20}")
    elif mode == "TRAKE":
        print(f"{'Event #':<8} {'Video ID':<12} {'Frame':<8} {'Time(s)':<8} {'R-Score':<9} {'Event Description'}")
        print("-" * 90)
        for r in results:
            ev_idx = r.get("event_index", 0) + 1
            vid = str(r.get("video_id", ""))
            fid = str(r.get("frame_id", ""))
            ts = f"{float(r.get('timestamp', 0.0)):.1f}s"
            rscore = f"{float(r.get('r_score', r.get('score', 0.0))):.4f}"
            ev_text = str(r.get("event_text", ""))[:35]
            print(f"#{ev_idx:<7} {vid:<12} {fid:<8} {ts:<8} {rscore:<9} {ev_text}")
    else:
        print(f"{'Rank':<5} {'Video ID':<12} {'Frame':<8} {'Keyframe':<10} {'Time(s)':<8} {'R-Score':<9}")
        print("-" * 90)
        for idx, r in enumerate(results, start=1):
            vid = str(r.get("video_id", ""))
            fid = str(r.get("frame_id", ""))
            kf_val = r.get("keyframe_id", 0)
            try:
                kf_str = f"{int(kf_val):03d}"
            except Exception:
                kf_str = str(kf_val)
            ts = f"{float(r.get('timestamp', 0.0)):.1f}s"
            rscore = f"{float(r.get('r_score', r.get('score', 0.0))):.4f}"
            print(f"#{idx:<4} {vid:<12} {fid:<8} {kf_str:<10} {ts:<8} {rscore:<9}")

    print("=" * 90 + "\n")


if __name__ == "__main__":
    asyncio.run(_run())
