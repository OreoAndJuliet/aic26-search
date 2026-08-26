import json
import httpx
import os
import shutil
import zipfile
from pathlib import Path

# Paths
BACKEND_DIR = Path(__file__).resolve().parent.parent
QUERIES_FILE = BACKEND_DIR / "data" / "aic26_round1_queries.json"
SUBMISSION_DIR = BACKEND_DIR / "data" / "submission"
ZIP_FILE = BACKEND_DIR / "data" / "submission_round1.zip"

SEARCH_API_URL = "http://127.0.0.1:8000/api/v1/search"
EXPORT_API_URL = "http://127.0.0.1:8000/api/v1/export/submission/from-search"

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
    with httpx.Client(timeout=300.0) as client:
        for q in queries:
            qid_str = q["id"]       # e.g., query-p1-1-kis
            task_type = q["type"]   # KIS, QA, TRAKE
            text = q["text"]
            
            print(f"\nProcessing {qid_str} ({task_type})...")
            
            # Extract numeric query_id from the string (e.g., query-p1-1-kis -> 1)
            parts = qid_str.split('-')
            try:
                query_id_num = int(parts[2])
            except ValueError:
                query_id_num = 1
                
            # For TRAKE, the text might be multiple events. We just use the whole text for search in this automation.
            # Real TRAKE requires passing multiple queries to the API, but our backend handles KIS and QA out of the box.
            if task_type == "TRAKE":
                # Our backend doesn't fully support automated TRAKE with a single text yet, 
                # but we'll try to just send the first event to get some results so the CSV is valid.
                text = q["events"][0] if "events" in q else text

            # Fix task type mapping for VQA
            api_task_type = "VQA" if task_type == "QA" else task_type
            
            # 1. Search
            payload = {
                "text": text,
                "type": api_task_type,
                "top_k": 100
            }
            if task_type == "TRAKE" and "events" in q:
                payload["events"] = q["events"]
            if api_task_type == "VQA":
                payload["question"] = text
            
            try:
                resp = client.post(SEARCH_API_URL, json=payload)
                resp.raise_for_status()
                search_data = resp.json()
            except Exception as e:
                print(f"  [ERROR] Search failed for {qid_str}: {e}")
                continue
                
            # 2. Export to CSV using our backend endpoint
            export_payload = {
                "task_type": task_type,
                "search_response": search_data,
                "team_session_id": "auto-solver",
                "query_id": query_id_num
            }
            
            try:
                export_resp = client.post(EXPORT_API_URL, json=export_payload)
                export_resp.raise_for_status()
                export_data = export_resp.json()
                
                if export_data.get("status") == "SUCCESS":
                    csv_path = export_data.get("csv_path")
                    # Move this CSV to our global submission dir
                    if csv_path and os.path.exists(csv_path):
                        target_csv = SUBMISSION_DIR / f"{qid_str}.csv"
                        shutil.copy(csv_path, target_csv)
                        print(f"  [SUCCESS] Saved {target_csv.name}")
                        success_count += 1
                else:
                    print(f"  [ERROR] Export failed: {export_data.get('validation_errors')}")
            except Exception as e:
                print(f"  [ERROR] Export request failed for {qid_str}: {e}")

    # 3. Zip everything
    print("\nZipping results...")
    with zipfile.ZipFile(ZIP_FILE, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(SUBMISSION_DIR):
            for file in files:
                file_path = os.path.join(root, file)
                # Ensure the folder structure in zip is 'submission/query-...'
                arcname = os.path.join("submission", file)
                zf.write(file_path, arcname)
                
    print(f"\nDone! Successfully processed {success_count}/{len(queries)} queries.")
    print(f"Submission zip ready at: {ZIP_FILE}")

if __name__ == "__main__":
    main()
