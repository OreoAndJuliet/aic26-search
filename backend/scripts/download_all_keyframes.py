"""High-speed multi-connection HTTP Range downloader for remaining Keyframes."""

import os
import sys
import time
import zipfile
import threading
from pathlib import Path
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

BACKEND_DIR = Path(__file__).resolve().parent.parent
INBOX_DIR = BACKEND_DIR / "data" / "inbox"
KEYFRAMES_DIR = BACKEND_DIR / "static" / "keyframes"

DATASETS_TO_DOWNLOAD = ["L23", "L25", "L26", "L27"]
BASE_URL = "https://aic-data.ledo.io.vn/Keyframes_{dataset}.zip"
NUM_PARTS = 16
MAX_CONCURRENT_WORKERS = 8

def get_file_size(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return int(resp.headers.get("Content-Length", 0))

def download_chunk(url, start_byte, end_byte, chunk_idx, part_file, progress_tracker):
    expected_len = end_byte - start_byte + 1
    existing_len = part_file.stat().st_size if part_file.exists() else 0
    
    if existing_len >= expected_len:
        progress_tracker.add(existing_len)
        return True

    actual_start = start_byte + existing_len
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Range": f"bytes={actual_start}-{end_byte}"
    }
    progress_tracker.add(existing_len)
    
    for attempt in range(8):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=45) as resp, open(part_file, "ab" if existing_len > 0 else "wb") as f:
                while True:
                    data = resp.read(1024 * 512)
                    if not data:
                        break
                    f.write(data)
                    progress_tracker.add(len(data))
            return True
        except Exception as e:
            if attempt == 7:
                print(f"\n[Part {chunk_idx:02d}] Failed after 8 attempts: {e}")
                raise
            time.sleep(1 + attempt * 2)

class ProgressTracker:
    def __init__(self, total_bytes):
        self.total_bytes = total_bytes
        self.downloaded = 0
        self.lock = threading.Lock()
        self.start_time = time.time()
        self.last_print = 0

    def add(self, n):
        with self.lock:
            self.downloaded += n
            now = time.time()
            if now - self.last_print > 0.5 or self.downloaded >= self.total_bytes:
                self.last_print = now
                elapsed = now - self.start_time
                speed = (self.downloaded / (1024 * 1024 * elapsed)) if elapsed > 0 else 0
                pct = (self.downloaded / self.total_bytes * 100) if self.total_bytes > 0 else 0
                mb_down = self.downloaded / (1024 * 1024)
                mb_total = self.total_bytes / (1024 * 1024)
                eta = ((self.total_bytes - self.downloaded) / (speed * 1024 * 1024)) if speed > 0 else 0
                print(f"\r[Downloader] {mb_down:.1f}/{mb_total:.1f} MB ({pct:.1f}%) | Speed: {speed:.2f} MB/s | ETA: {eta:.0f}s ", end="", flush=True)

def download_dataset(dataset):
    url = BASE_URL.format(dataset=dataset)
    zip_name = f"Keyframes_{dataset}.zip"
    zip_path = INBOX_DIR / zip_name
    
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    
    print(f"\n--- Downloading {dataset} ---")
    try:
        total_size = get_file_size(url)
    except Exception as e:
        print(f"Failed to get file size for {dataset}: {e}")
        return
        
    if zip_path.exists() and zip_path.stat().st_size == total_size:
        print(f"{zip_name} already exists and is complete.")
        return zip_path
        
    temp_dir = INBOX_DIR / f"_{dataset}_parts"
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    part_size = total_size // NUM_PARTS
    chunks = []
    for i in range(NUM_PARTS):
        start = i * part_size
        end = (start + part_size - 1) if i < NUM_PARTS - 1 else (total_size - 1)
        part_file = temp_dir / f"part_{i:02d}.bin"
        chunks.append((i, start, end, part_file))
        
    tracker = ProgressTracker(total_size)
    print(f"Starting parallel download with {MAX_CONCURRENT_WORKERS} streams...")
    
    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_WORKERS) as executor:
        futures = {
            executor.submit(download_chunk, url, start, end, idx, pfile, tracker): idx
            for idx, start, end, pfile in chunks
        }
        for future in as_completed(futures):
            future.result()
            
    print(f"\nMerging into {zip_name}...")
    with open(zip_path, "wb") as out_f:
        for idx, start, end, pfile in chunks:
            with open(pfile, "rb") as in_f:
                while True:
                    buf = in_f.read(1024 * 1024 * 16)
                    if not buf:
                        break
                    out_f.write(buf)
            pfile.unlink()
    temp_dir.rmdir()
    print(f"Merge complete: {zip_path.stat().st_size / (1024*1024):.2f} MB")
    return zip_path

def extract_dataset(zip_path, dataset):
    if not zip_path:
        return
    print(f"\nExtracting {zip_path.name} to {KEYFRAMES_DIR}...")
    KEYFRAMES_DIR.mkdir(parents=True, exist_ok=True)
    
    with zipfile.ZipFile(zip_path, "r") as zf:
        namelist = zf.namelist()
        total_files = len(namelist)
        extracted = 0
        for i, member in enumerate(namelist):
            parts = Path(member).parts
            if len(parts) >= 2 and parts[-1].lower().endswith((".jpg", ".jpeg", ".png")):
                vid = parts[-2]
                fname = parts[-1]
                target_dir = KEYFRAMES_DIR / vid
                target_dir.mkdir(parents=True, exist_ok=True)
                target_file = target_dir / fname
                if not target_file.exists():
                    with zf.open(member) as src, open(target_file, "wb") as dst:
                        dst.write(src.read())
                    extracted += 1
            if (i + 1) % 1000 == 0 or i + 1 == total_files:
                print(f"\rExtracted: {i+1}/{total_files} items ({extracted} written)...", end="", flush=True)
    print(f"\nExtraction finished for {dataset}! Total new files written: {extracted}")

if __name__ == "__main__":
    for ds in DATASETS_TO_DOWNLOAD:
        zip_path = download_dataset(ds)
        extract_dataset(zip_path, ds)
