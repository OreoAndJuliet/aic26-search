"""Download and extract available video datasets (Videos_L21_a.zip, Videos_L22_a.zip)."""

import os
import sys
import time
import zipfile
import threading
from pathlib import Path
import urllib.request
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed

BACKEND_DIR = Path(r"C:\Users\junde\OneDrive\Desktop\TranKhoi\BachKhoa\DuAn_AIC\aic26-search\backend")
INBOX_DIR = BACKEND_DIR / "data" / "inbox"
STATIC_VIDEOS_DIR = BACKEND_DIR / "static" / "videos"
DATA_VIDEOS_DIR = BACKEND_DIR / "data" / "videos"
PROCESSED_DIR = INBOX_DIR / "processed"
USER_DOWNLOADS = Path(r"C:\Users\junde\Downloads")

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

def extract_video_zip(zip_path):
    print(f"\nExtracting video files from {zip_path.name}...")
    extracted_count = 0
    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.namelist():
            if member.lower().endswith(".mp4"):
                fname = Path(member).name
                dest1 = STATIC_VIDEOS_DIR / fname
                dest2 = DATA_VIDEOS_DIR / fname
                if not dest1.exists():
                    with zf.open(member) as src, open(dest1, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                if not dest2.exists():
                    shutil.copyfile(dest1, dest2)
                extracted_count += 1
                print(f"  -> Extracted video: {fname}")
    print(f"Extraction finished for {zip_path.name}: {extracted_count} MP4 videos.")

def process_local_zip(local_zip_path):
    print(f"\nProcessing existing local zip: {local_zip_path}")
    extract_video_zip(local_zip_path)
    dest = PROCESSED_DIR / local_zip_path.name
    if not dest.exists():
        shutil.copyfile(local_zip_path, dest)
        print(f"Copied {local_zip_path.name} -> {PROCESSED_DIR}")

def download_and_extract_video(url, zip_name):
    zip_path = INBOX_DIR / zip_name
    processed_path = PROCESSED_DIR / zip_name
    
    if processed_path.exists():
        print(f"{zip_name} already in processed. Checking extraction...")
        extract_video_zip(processed_path)
        return
        
    print(f"\n========================================================")
    print(f"Checking URL: {url}")
    total_size = get_file_size(url)
    print(f"Total size: {total_size / (1024*1024):.2f} MB")
    
    temp_dir = INBOX_DIR / f"_temp_parts_{Path(zip_name).stem}"
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
            
    print(f"\nMerging parts into {zip_name}...")
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
    extract_video_zip(zip_path)
    
    dest_zip = PROCESSED_DIR / zip_name
    if dest_zip.exists():
        dest_zip.unlink()
    zip_path.rename(dest_zip)
    print(f"Moved {zip_name} -> processed/")

def main():
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    STATIC_VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    DATA_VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    
    # 1. Process local Videos_L21_a.zip
    l21_zip = USER_DOWNLOADS / "Videos_L21_a.zip"
    if l21_zip.exists():
        process_local_zip(l21_zip)
        
    # 2. Download and extract Videos_L22_a.zip
    url_l22 = "https://aic-data.ledo.io.vn/Videos_L22_a.zip"
    download_and_extract_video(url_l22, "Videos_L22_a.zip")
    
    print("\n========================================================")
    print("ALL AVAILABLE VIDEOS PROCESSED & EXTRACTED SUCCESSFULLY!")
    print("========================================================")

if __name__ == "__main__":
    main()
