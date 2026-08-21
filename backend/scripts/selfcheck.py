"""Run KIS vector parsing and CLIP alignment self-checks."""

import json
import logging
import os
import sys
import warnings

# Suppress all warnings and verbose output before any imports
os.environ["USE_FAST"] = "1"
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
os.environ["HF_HUB_DISABLE_SYMLINKS"] = "1"
warnings.filterwarnings("ignore")

# Redirect stderr to suppress PIL/HF warnings

sys.stderr = open(os.devnull, 'w')  # noqa: SIM115 - intentional global stderr redirect for CLI suppression

# Set up null handler for logging to suppress all PIL/transformers/HF warnings
logging.basicConfig(level=logging.ERROR)
logging.getLogger("PIL").setLevel(logging.ERROR)
logging.getLogger("transformers").setLevel(logging.ERROR)
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.services.kis_engine import kis_engine
from app.services.kis_selfcheck import assert_selfcheck_passes, run_kis_selfcheck


def main() -> int:
    try:
        kis_engine.initialize()
        report = run_kis_selfcheck(kis_engine, include_alignment=True)
        assert_selfcheck_passes(report)
    except Exception as exc:  # noqa: BLE001 - CLI boundary reports any startup/check failure
        print(json.dumps({"status": "failed", "error": str(exc)}))
        return 1

    print(json.dumps(report.to_dict(), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
