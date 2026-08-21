"""HTTP smoke tests from TEST_GUIDE section 4 (mock or live server)."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
import warnings
from collections.abc import Callable
from pathlib import Path

# Suppress all warnings before any imports
warnings.filterwarnings("ignore")

import httpx
import pytest
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Suppress all logging output to prevent zip_ingest and other warnings
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"

# Configure logging to only show CRITICAL errors
logging.basicConfig(level=logging.CRITICAL, force=True)
logging.getLogger("app.services.zip_ingest").setLevel(logging.CRITICAL)
logging.getLogger("app").setLevel(logging.CRITICAL)

# Redirect stderr to suppress all log output

sys._original_stderr = sys.stderr
sys.stderr = open(os.devnull, 'w')  # noqa: SIM115 - intentional global stderr redirect for test suppression


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _collect_requirement_gaps(project_root: Path) -> list[dict[str, str]]:
    """Report implementation gaps against the 2026 AIC requirement docs in New folder."""
    findings: list[dict[str, str]] = []
    requirement_dir = project_root / "New folder" / "_extracted"
    doc_present = bool(requirement_dir.exists())

    frontend_pkg = project_root / "package.json"
    frontend_sources = project_root / "src"
    frontend_missing = not frontend_pkg.exists() and not frontend_sources.exists()

    if frontend_missing:
        findings.extend(
            [
                {
                    "requirement": "Frontend Web App (React/Vite)",
                    "status": "missing",
                    "details": "No package.json or frontend src/ folder was found; the requirement expects a Web UI.",
                },
                {
                    "requirement": "Search View + Result Grid UI",
                    "status": "missing",
                    "details": "There is no browser search interface or visual result grid matching the requirement.",
                },
                {
                    "requirement": "Local Video Player Modal / timestamp navigation",
                    "status": "missing",
                    "details": "No click-to-play local video modal with jump-to-frame behavior was found.",
                },
                {
                    "requirement": "Submission cart + CSV/ZIP export workflow",
                    "status": "missing",
                    "details": "The backend can export results, but the requirement requires an actual browser submission workflow.",
                },
                {
                    "requirement": "Human-in-the-loop review workflow",
                    "status": "missing",
                    "details": "No operator review screen or review workflow was found in the codebase.",
                },
            ]
        )
    else:
        review_ui_present = any(
            "review" in str(path).lower() for path in (project_root / "app").rglob("*.py")
        ) or any("review" in str(path).lower() for path in (project_root / "scripts").glob("*.py"))
        if not review_ui_present:
            findings.append(
                {
                    "requirement": "Human-in-the-loop review workflow",
                    "status": "missing",
                    "details": "No operator review screen or review workflow was found in the codebase.",
                }
            )

    if not doc_present:
        findings.append(
            {
                "requirement": "2026 requirement documents",
                "status": "missing",
                "details": "No requirement files were found under New folder/_extracted.",
            }
        )

    return findings


def _run_mock_checks(client: TestClient) -> list[str]:
    passed: list[str] = []

    response = client.get("/")
    _assert(response.status_code == 200, "GET / failed")
    payload = response.json()
    _assert(payload.get("status") == "online", "GET / missing status=online")
    passed.append("GET /")

    response = client.get("/health")
    _assert(response.status_code == 200, "GET /health failed")
    passed.append("GET /health")

    response = client.get("/api/v1/system/info")
    _assert(response.status_code == 200, "GET /api/v1/system/info failed")
    _assert("kis" in response.json(), "system/info missing kis block")
    passed.append("GET /api/v1/system/info")

    response = client.post(
        "/api/v1/search/kis",
        json={"query": "a person walking in a room", "top_k": 2},
    )
    _assert(response.status_code == 200, "POST /api/v1/search/kis failed")
    kis_payload = response.json()
    _assert(kis_payload.get("status") == "success", "KIS status not success")
    _assert(len(kis_payload.get("results", [])) == 2, "KIS top_k=2 expected 2 results")
    passed.append("POST /api/v1/search/kis")

    response = client.post(
        "/api/v1/search/kis",
        json={"query_text": "a person walking in a room", "top_k": 1},
    )
    _assert(response.status_code == 200, "POST /api/v1/search/kis query_text alias failed")
    passed.append("POST /api/v1/search/kis (query_text alias)")

    response = client.post(
        "/api/v1/search/kis",
        json={"query": "   ", "top_k": 5},
    )
    _assert(response.status_code == 422, "blank KIS query should return 422")
    passed.append("POST /api/v1/search/kis (blank query -> 422)")

    response = client.post(
        "/api/v1/search/kis",
        json={"query": "test", "top_k": 0},
    )
    _assert(response.status_code == 422, "top_k=0 should return 422")
    passed.append("POST /api/v1/search/kis (top_k=0 -> 422)")

    response = client.post(
        "/api/v1/search",
        json={"type": "KIS", "text": "a person walking in a room", "top_k": 1},
    )
    _assert(response.status_code == 200, "unified KIS search failed")
    unified = response.json()
    _assert(unified.get("type") == "KIS", "unified search type should be KIS")
    _assert(unified.get("request_id"), "unified KIS missing request_id")
    passed.append("POST /api/v1/search (KIS)")

    response = client.post(
        "/api/v1/search",
        json={
            "type": "VQA",
            "text": "a person in a room",
            "question": "How many people are visible?",
            "top_k": 1,
        },
    )
    _assert(response.status_code == 200, "unified VQA search failed")
    vqa_payload = response.json()
    _assert(vqa_payload.get("type") == "VQA", "unified search type should be VQA")
    passed.append("POST /api/v1/search (VQA)")

    response = client.post(
        "/api/v1/search",
        json={
            "type": "TRAKE",
            "events": ["enters room", "sits down"],
            "top_k_per_event": 5,
        },
    )
    _assert(response.status_code == 200, "unified TRAKE search failed")
    trake_payload = response.json()
    _assert(trake_payload.get("type") == "TRAKE", "unified search type should be TRAKE")
    _assert(trake_payload.get("trake"), "TRAKE response missing trake block")
    passed.append("POST /api/v1/search (TRAKE)")

    thumbnail_url = unified["results"][0]["thumbnail_url"]
    image_response = client.get(thumbnail_url)
    _assert(image_response.status_code == 200, "keyframe thumbnail GET failed")
    _assert(
        image_response.headers.get("content-type", "").startswith("image/"),
        "keyframe should return image content-type",
    )
    passed.append("GET keyframe thumbnail")

    response = client.post(
        "/api/v1/export/submission",
        json={
            "task_type": "KIS",
            "query_id": 1,
            "results": [
                {"video_id": "video-1", "frame_id": 10, "answer": ""},
                {"video_id": "video-1", "frame_id": 20, "answer": ""},
            ],
        },
    )
    _assert(response.status_code == 200, "export submission failed")
    export_payload = response.json()
    _assert(export_payload.get("status") == "SUCCESS", "export should succeed for valid KIS")
    passed.append("POST /api/v1/export/submission (KIS)")

    response = client.post(
        "/api/v1/export/submission",
        json={
            "task_type": "INVALID",
            "query_id": 1,
            "results": [{"video_id": "video-1", "frame_id": 10, "answer": ""}],
        },
    )
    _assert(response.status_code == 200, "invalid export should still return HTTP 200")
    invalid_export = response.json()
    _assert(invalid_export.get("status") == "FAILED", "invalid task_type should fail validation")
    passed.append("POST /api/v1/export/submission (invalid task_type)")

    response = client.post(
        "/api/v1/export/submission/from-search",
        json={
            "task_type": "KIS",
            "query_id": 1,
            "search_response": unified,
        },
    )
    _assert(response.status_code == 200, "export from-search failed")
    _assert(response.json().get("status") == "SUCCESS", "from-search export should succeed")
    passed.append("POST /api/v1/export/submission/from-search")

    return passed


def _run_live_checks(base_url: str, timeout: float) -> list[str]:
    passed: list[str] = []
    base = base_url.rstrip("/")

    with httpx.Client(base_url=base, timeout=timeout) as client:
        checks: list[tuple[str, Callable[[httpx.Client], None]]] = [
            ("GET /", lambda c: _assert(c.get("/").status_code == 200, "GET / failed")),
            ("GET /health", lambda c: _assert(c.get("/health").status_code == 200, "GET /health failed")),
            (
                "GET /api/v1/system/info",
                lambda c: _assert(
                    c.get("/api/v1/system/info").status_code == 200,
                    "GET /api/v1/system/info failed",
                ),
            ),
            (
                "POST /api/v1/search/kis",
                lambda c: _assert(
                    c.post(
                        "/api/v1/search/kis",
                        json={"query": "a person walking in a room", "top_k": 3},
                    ).status_code
                    == 200,
                    "POST /api/v1/search/kis failed",
                ),
            ),
            (
                "POST /api/v1/search (KIS)",
                lambda c: _assert(
                    c.post(
                        "/api/v1/search",
                        json={"type": "KIS", "text": "a person walking in a room", "top_k": 3},
                    ).status_code
                    == 200,
                    "POST /api/v1/search KIS failed",
                ),
            ),
            (
                "POST /api/v1/search (TRAKE)",
                lambda c: _assert(
                    c.post(
                        "/api/v1/search",
                        json={
                            "type": "TRAKE",
                            "events": ["a person enters a room", "the person sits down"],
                            "top_k_per_event": 5,
                        },
                    ).status_code
                    == 200,
                    "POST /api/v1/search TRAKE failed",
                ),
            ),
            (
                "POST /api/v1/search/kis blank query -> 422",
                lambda c: _assert(
                    c.post("/api/v1/search/kis", json={"query": "   ", "top_k": 5}).status_code
                    == 422,
                    "blank query should return 422",
                ),
            ),
        ]

        for label, check in checks:
            check(client)
            passed.append(label)

    return passed


def main() -> int:
    parser = argparse.ArgumentParser(description="Run TEST_GUIDE HTTP smoke checks.")
    parser.add_argument(
        "--base-url",
        default="",
        help="Live server base URL (default: in-process TestClient with mock KIS backend)",
    )
    parser.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout for live mode")
    parser.add_argument(
        "--requirement-report",
        action="store_true",
        help="Print the remaining AIC 2026 requirement gaps against the New folder docs.",
    )
    args = parser.parse_args()

    try:
        project_root = Path(__file__).resolve().parents[1]
        if args.requirement_report:
            report = {
                "status": "requirements-check",
                "project_root": str(project_root),
                "missing_requirements": _collect_requirement_gaps(project_root),
            }
            print(json.dumps(report, indent=2, ensure_ascii=False))
            return 0

        if args.base_url:
            passed = _run_live_checks(args.base_url, args.timeout)
            mode = "live"
        else:
            from tests.conftest import _install_mock_kis_backend

            monkeypatch = pytest.MonkeyPatch()
            with tempfile.TemporaryDirectory(prefix="test-guide-http-") as tmp_dir:
                _install_mock_kis_backend(monkeypatch, Path(tmp_dir))

                from main import app

                with TestClient(app, raise_server_exceptions=True) as client:
                    passed = _run_mock_checks(client)
            monkeypatch.undo()
            mode = "mock"

        print(
            json.dumps(
                {
                    "status": "ok",
                    "mode": mode,
                    "checks_passed": len(passed),
                    "checks": passed,
                },
                indent=2,
            )
        )
        return 0
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        print(json.dumps({"status": "failed", "error": str(exc)}))
        return 1
    finally:
        # Restore original stderr
        if hasattr(sys, '_original_stderr'):
            sys.stderr = sys._original_stderr


if __name__ == "__main__":
    sys.exit(main())
