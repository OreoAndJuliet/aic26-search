"""High-speed multi-threaded downloader & auto-extractor for Keyframes_L26_a.zip and Keyframes_L26_b.zip."""

import os
import sys
import time
import zipfile
import threading
from pathlib import Path
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

BACKEND_DIR = Path(r"C:\Users\junde\OneDrive\Desktop\TranKhoi\BachKhoa\DuAn_AIC\aic26-search\backend")
INBOX_DIR = BACKEND_DIR / "data" / "inbox"
KEYFRAMES_DIR = BACKEND_DIR / "static" / "keyframes"
PROCESSED_DIR = INBOX_DIR / "processed"

NUM_PARTS = 16
MAX_CONCURRENT_WORKERS = 8

def get_file_size(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return int(resp.headers.get("Content-Length", 0))

class ProgressTracker:
    def __init__(self, total_bytes):
        self.total_bytes = total_bytes
        self.downloaded = 0
        self.lock = threading.Lock()
        self.start_time = time.time()

    def add(self, n):
        with self.lock:
            self.downloaded += n
            elapsed = time.time() - self.start_time
            if elapsed > 0:
                speed_mb = (self.downloaded / (1024 * 1024)) / elapsed
                percent = (self.downloaded / self.total_bytes) * 100 if self.total_bytes else 0
                dl_mb = self.downloaded / (1024 * 1024)
                tot_mb = self.total_bytes / (1024 * 1024)
                print(f"\rProgress: {dl_mb:.1f}/{tot_mb:.1f} MB ({percent:.1f}%) | Speed: {speed_mb:.2f} MB/s", end="", flush=True)

def download_chunk(url, start_byte, end_byte, chunk_idx, part_file, progress_tracker):
    expected_len = end_byte - start_byte + 1
    existing_len = part_file.stat().st_size if part_file.exists() else 0
    
    if existing_len >= expected_len:
        progress_tracker.add(existing_len)
        return True

    actual_start = start_byte + existing_len
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
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

def download_and_extract_url(url, zip_path):
    print(f"\n========================================================")
    print(f"Checking URL: {url}")
    total_size = get_file_size(url)
    print(f"Total size: {total_size / (1024*1024):.2f} MB")
    
    temp_dir = INBOX_DIR / f"_temp_parts_{zip_path.stem}"
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    chunk_size = total_size // NUM_PARTS
    parts = []
    progress_tracker = ProgressTracker(total_size)
    
    for i in range(NUM_PARTS):
        start = i * chunk_size
        end = total_size - 1 if i == NUM_PARTS - 1 else (i + 1) * chunk_size - 1
        part_file = temp_dir / f"part_{i:02d}.bin"
        parts.append((start, end, i, part_file))
        
    print(f"Starting multi-threaded download ({NUM_PARTS} parts, {MAX_CONCURRENT_WORKERS} workers)...")
    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_WORKERS) as executor:
        futures = {
            executor.submit(download_chunk, url, start, end, idx, pfile, progress_tracker): idx
            for start, end, idx, pfile in parts
        }
        for future in as_completed(futures):
            future.result()
            
    print(f"\nMerging parts into {zip_path.name}...")
    with open(zip_path, "wb") as outfile:
        for _, _, _, pfile in parts:
            with open(pfile, "rb") as infile:
                while True:
                    buf = infile.read(1024 * 1024 * 4)
                    if not buf:
                        break
                    outfile.write(buf)
            pfile.unlink()
    try:
        temp_dir.rmdir()
    except Exception:
        pass
        
    print(f"Merged successfully ({zip_path.stat().st_size / (1024*1024):.2f} MB).")
    
    print(f"Extracting keyframes directly to {KEYFRAMES_DIR}...")
    with zipfile.ZipFile(zip_path, "r") as zf:
        namelist = zf.namelist()
        total_files = len(namelist)
        extracted = 0
        for i, member in enumerate(namelist):
            parts_p = Path(member).parts
            if len(parts_p) >= 2 and parts_p[-1].lower().endswith((".jpg", ".jpeg", ".png")):
                vid = parts_p[-2]
                fname = parts_p[-1]
                target_dir = KEYFRAMES_DIR / vid
                target_dir.mkdir(parents=True, exist_ok=True)
                target_file = target_dir / fname
                if not target_file.exists():
                    with zf.open(member) as src, open(target_file, "wb") as dst:
                        dst.write(src.read())
                    extracted += 1
            if (i + 1) % 500 == 0 or i + 1 == total_files:
                print(f"\rExtracted: {i+1}/{total_files} items ({extracted} written)...", end="", flush=True)
    print(f"\nExtraction finished for {zip_path.name}! Total new files written: {extracted}")
    
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    dest_zip = PROCESSED_DIR / zip_path.name
    if dest_zip.exists():
        dest_zip.unlink()
    zip_path.rename(dest_zip)
    print(f"Moved {zip_path.name} -> processed/")

def main():
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    KEYFRAMES_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    
    # 1. Download Keyframes_L26_a.zip and Keyframes_L26_b.zip
    for part in ["Keyframes_L26_a.zip", "Keyframes_L26_b.zip"]:
        zip_path = INBOX_DIR / part
        processed_path = PROCESSED_DIR / part
        if processed_path.exists():
            print(f"{part} already processed. Skipping.")
            continue
        url = f"https://aic-data.ledo.io.vn/{part}"
        download_and_extract_url(url, zip_path)

    print("\n========================================================")
    print("ALL MISSING DATA DOWNLOADED & EXTRACTED SUCCESSFULLY!")
    print("========================================================")

if __name__ == "__main__":
    main()
