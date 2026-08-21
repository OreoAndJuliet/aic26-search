"""Download and install Keyframes_L22 directly from official Excel links."""

import os
import sys
import time
import zipfile
from pathlib import Path
import urllib.request

# Setup paths
BACKEND_DIR = Path(__file__).resolve().parent.parent
INBOX_DIR = BACKEND_DIR / "data" / "inbox"
KEYFRAMES_DIR = BACKEND_DIR / "static" / "keyframes"
ZIP_PATH = INBOX_DIR / "Keyframes_L22.zip"
URL = "https://aic-data.ledo.io.vn/Keyframes_L22.zip"

def download_l22():
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    
    if ZIP_PATH.exists() and ZIP_PATH.stat().st_size > 1_700_000_000:
        print(f"[1/3] {ZIP_PATH.name} already exists ({ZIP_PATH.stat().st_size / (1024*1024):.2f} MB). Skipping download.")
        return True

    print(f"[1/3] Downloading {URL} -> {ZIP_PATH} ...")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    req = urllib.request.Request(URL, headers=headers)
    
    start_time = time.time()
    with urllib.request.urlopen(req, timeout=60) as resp, open(ZIP_PATH, "wb") as out_file:
        total_size = int(resp.headers.get("Content-Length", 0))
        downloaded = 0
        chunk_size = 1024 * 1024 * 4  # 4MB chunks
        
        while True:
            chunk = resp.read(chunk_size)
            if not chunk:
                break
            out_file.write(chunk)
            downloaded += len(chunk)
            
            elapsed = time.time() - start_time
            speed = downloaded / (1024 * 1024 * elapsed) if elapsed > 0 else 0
            pct = (downloaded / total_size * 100) if total_size > 0 else 0
            
            print(f"\rDownloading: {downloaded / (1024*1024):.1f}MB / {total_size / (1024*1024):.1f}MB ({pct:.1f}%) @ {speed:.2f} MB/s", end="", flush=True)
            
    print(f"\nDownload completed in {time.time() - start_time:.1f}s.")
    return True

def extract_l22():
    print(f"\n[2/3] Extracting {ZIP_PATH.name} into {KEYFRAMES_DIR} ...")
    KEYFRAMES_DIR.mkdir(parents=True, exist_ok=True)
    
    with zipfile.ZipFile(ZIP_PATH, "r") as zf:
        namelist = zf.namelist()
        total_files = len(namelist)
        print(f"Total files in archive: {total_files}")
        
        extracted_count = 0
        for i, member in enumerate(namelist):
            # Member could be Keyframes_L22/L22_V001/0001.jpg or L22_V001/0001.jpg
            parts = Path(member).parts
            if len(parts) >= 2 and parts[-1].lower().endswith((".jpg", ".jpeg", ".png")):
                # Find video folder (e.g. L22_V001)
                vid_folder = parts[-2]
                filename = parts[-1]
                
                target_folder = KEYFRAMES_DIR / vid_folder
                target_folder.mkdir(parents=True, exist_ok=True)
                target_file = target_folder / filename
                
                if not target_file.exists():
                    with zf.open(member) as source, open(target_file, "wb") as target:
                        target.write(source.read())
                    extracted_count += 1
            
            if (i + 1) % 500 == 0 or i + 1 == total_files:
                print(f"\rExtracted: {i + 1}/{total_files} items ({extracted_count} written)...", end="", flush=True)
                
    print(f"\nExtraction complete! {extracted_count} new images written.")

def verify_l22():
    print(f"\n[3/3] Verifying L22 keyframe directories in {KEYFRAMES_DIR} ...")
    l22_dirs = sorted([d for d in KEYFRAMES_DIR.iterdir() if d.is_dir() and d.name.startswith("L22")])
    total_imgs = 0
    print(f"Found {len(l22_dirs)} L22 video directories:")
    for d in l22_dirs[:5]:
        imgs = len(list(d.glob("*.jpg")))
        total_imgs += imgs
        print(f"  - {d.name}: {imgs} images")
    if len(l22_dirs) > 5:
        print(f"  ... and {len(l22_dirs) - 5} more directories.")
        for d in l22_dirs[5:]:
            total_imgs += len(list(d.glob("*.jpg")))
    print(f"Total L22 images installed: {total_imgs}")

if __name__ == "__main__":
    download_l22()
    extract_l22()
    verify_l22()
