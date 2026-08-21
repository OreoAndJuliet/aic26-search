"""Extract zip bundles from data/inbox into static/ (manual CLI)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.services.zip_ingest import zip_ingest_service


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract AIC keyframe/video zips from inbox.")
    parser.parse_args()

    results = zip_ingest_service.ingest_inbox()
    payload = {
        "status": "ok",
        "processed": [
            {
                "zip": item.zip_name,
                "target": item.target,
                "files_written": item.files_written,
                "skipped_existing": item.skipped_existing,
            }
            for item in results
        ],
    }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
