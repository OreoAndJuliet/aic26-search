"""Compute KIS R-Score metrics for one query."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.services.kis_engine import kis_engine
from app.services.kis_rscore import build_rscore_report
from app.services.translator import translator


async def _run(query: str, top_k: int) -> dict:
    from app.features.search.retrieval import run_kis_retrieval
    kis_engine.initialize()
    translation = await translator.translate_async(query)
    results, metrics = run_kis_retrieval(translation.text, top_k, raw_query=query)
    report = build_rscore_report(results)
    return {
        "query": query,
        "translated_query": translation.text,
        "translation_applied": translation.applied,
        "metrics": metrics,
        "rscore": report,
        "top_results": results[:5],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Compute KIS Top-k R-Score metrics.")
    parser.add_argument("query", help="Search query text")
    parser.add_argument("--top-k", type=int, default=100, help="Number of ranked results")
    args = parser.parse_args()

    try:
        payload = asyncio.run(_run(args.query, args.top_k))
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        print(json.dumps({"status": "failed", "error": str(exc)}))
        return 1

    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
