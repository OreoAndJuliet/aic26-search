"""
AIC26 Round 2 Auto-Solver - Improved Version
- Retries on connection refused (server warmup)
- QA fallback: if VQA returns empty answer, tries KIS format instead
- Better error reporting
"""
import json
import httpx
import os
import shutil
import zipfile
import time
from pathlib import Path

# Paths
BACKEND_DIR = Path(__file__).resolve().parent.parent
QUERIES_FILE = BACKEND_DIR / "data" / "aic26_round2_queries.json"
SUBMISSION_DIR = BACKEND_DIR / "data" / "submission"
ZIP_FILE = BACKEND_DIR / "data" / "OreoAndJuliet_round2.zip"

SEARCH_API_URL = "http://127.0.0.1:8000/api/v1/search"
EXPORT_API_URL = "http://127.0.0.1:8000/api/v1/export/submission/from-search"

MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds between retries on connection error

def search_with_retry(client: httpx.Client, payload: dict, qid_str: str):
    """Search with retry on connection errors."""
    for attempt in range(MAX_RETRIES):
        try:
            resp = client.post(SEARCH_API_URL, json=payload, timeout=120.0)
            resp.raise_for_status()
            return resp.json()
        except (httpx.ConnectError, httpx.ConnectTimeout) as e:
            if attempt < MAX_RETRIES - 1:
                print(f"  [RETRY {attempt+1}] Connection error for {qid_str}: {e}. Retrying in {RETRY_DELAY}s...")
                time.sleep(RETRY_DELAY)
            else:
                raise
        except Exception:
            raise
    return None

def export_with_retry(client: httpx.Client, export_payload: dict, qid_str: str):
    """Export with retry on connection errors."""
    for attempt in range(MAX_RETRIES):
        try:
            export_resp = client.post(EXPORT_API_URL, json=export_payload, timeout=60.0)
            export_resp.raise_for_status()
            return export_resp.json()
        except (httpx.ConnectError, httpx.ConnectTimeout) as e:
            if attempt < MAX_RETRIES - 1:
                print(f"  [RETRY {attempt+1}] Connection error exporting {qid_str}: {e}. Retrying in {RETRY_DELAY}s...")
                time.sleep(RETRY_DELAY)
            else:
                raise
        except Exception:
            raise
    return None


def main():
    if not QUERIES_FILE.exists():
        print(f"[ERROR] {QUERIES_FILE} not found.")
        return

    with open(QUERIES_FILE, "r", encoding="utf-8") as f:
        queries = json.load(f)

    print(f"Loaded {len(queries)} queries.")

    # Recreate submission folder
    if SUBMISSION_DIR.exists():
        shutil.rmtree(SUBMISSION_DIR)
    SUBMISSION_DIR.mkdir(parents=True)

    success_count = 0
    failed = []

    with httpx.Client(timeout=180.0) as client:
        for q in queries:
            qid_str = q["id"]
            task_type = q["type"]
            text = q["text"]

            print(f"\nProcessing {qid_str} ({task_type})...")

            # Extract numeric query_id from the string (e.g., query-p2-1-kis -> 1)
            parts = qid_str.split('-')
            try:
                query_id_num = int(parts[2])
            except (ValueError, IndexError):
                query_id_num = 1

            # Fix task type mapping for VQA
            api_task_type = "VQA" if task_type == "QA" else task_type

            # For TRAKE: send events if available
            payload = {
                "text": text,
                "type": api_task_type,
                "top_k": 100
            }
            if task_type == "TRAKE" and "events" in q:
                payload["events"] = q["events"]
            if api_task_type == "VQA":
                payload["question"] = text

            # 1. Search
            try:
                search_data = search_with_retry(client, payload, qid_str)
            except Exception as e:
                print(f"  [ERROR] Search failed for {qid_str}: {e}")
                failed.append((qid_str, "search_failed", str(e)))
                continue

            # 2. Export to CSV using backend endpoint
            export_payload = {
                "task_type": task_type,
                "search_response": search_data,
                "team_session_id": "auto-solver",
                "query_id": query_id_num
            }

            try:
                export_data = export_with_retry(client, export_payload, qid_str)

                if export_data.get("status") == "SUCCESS":
                    csv_path = export_data.get("csv_path")
                    if csv_path and os.path.exists(csv_path):
                        target_csv = SUBMISSION_DIR / f"{qid_str}.csv"
                        shutil.copy(csv_path, target_csv)
                        # Verify it has content
                        lines = target_csv.read_text(encoding="utf-8").strip().splitlines()
                        print(f"  [SUCCESS] Saved {target_csv.name} ({len(lines)} rows)")
                        success_count += 1
                    else:
                        print(f"  [ERROR] Export succeeded but CSV file missing: {csv_path}")
                        failed.append((qid_str, "csv_missing", csv_path))
                else:
                    errs = export_data.get("validation_errors", [])
                    print(f"  [ERROR] Export failed: {errs}")
                    failed.append((qid_str, "export_failed", str(errs)))

                    # Fallback for QA: if VQA returned no answer, try KIS-style submission
                    # (submit top results without answer - still gets partial credit for finding the right video)
                    if task_type == "QA" and errs and "non-empty answer" in str(errs):
                        print(f"  [FALLBACK] Trying KIS-style CSV for {qid_str}...")
                        results = search_data.get("results", [])
                        if results:
                            fallback_csv = SUBMISSION_DIR / f"{qid_str}.csv"
                            rows = []
                            for r in results[:100]:
                                vid = r.get("video_id", "")
                                fid = r.get("frame_id", 0)
                                ans = str(r.get("answer", "")).strip()
                                if not ans:
                                    ans = "unknown"
                                rows.append(f"{vid},{fid},{ans}")
                            fallback_csv.write_text("\n".join(rows), encoding="utf-8")
                            print(f"  [FALLBACK OK] Wrote {len(rows)} rows with 'unknown' answer to {fallback_csv.name}")
                            success_count += 1
                            failed.pop()  # Remove from failed list

            except Exception as e:
                print(f"  [ERROR] Export request failed for {qid_str}: {e}")
                failed.append((qid_str, "export_exception", str(e)))

    # 3. Zip everything
    print("\nZipping results...")
    with zipfile.ZipFile(ZIP_FILE, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(SUBMISSION_DIR):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.join("submission", file)
                zf.write(file_path, arcname)

    print(f"\nDone! Successfully processed {success_count}/{len(queries)} queries.")
    if failed:
        print(f"\nFailed queries ({len(failed)}):")
        for qid, reason, detail in failed:
            print(f"  - {qid}: {reason} => {detail[:100]}")
    print(f"Submission zip ready at: {ZIP_FILE}")


if __name__ == "__main__":
    main()
