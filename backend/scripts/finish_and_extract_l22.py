"""Finish remaining parts sequentially, merge Keyframes_L22.zip and extract."""

import os
import sys
import time
import zipfile
from pathlib import Path
import urllib.request

BACKEND_DIR = Path(__file__).resolve().parent.parent
INBOX_DIR = BACKEND_DIR / "data" / "inbox"
KEYFRAMES_DIR = BACKEND_DIR / "static" / "keyframes"
ZIP_PATH = INBOX_DIR / "Keyframes_L22.zip"
URL = "https://aic-data.ledo.io.vn/Keyframes_L22.zip"
NUM_PARTS = 16

def get_file_size():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    req = urllib.request.Request(URL, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return int(resp.headers.get("Content-Length", 0))

def finish_missing_parts():
    temp_dir = INBOX_DIR / "_l22_parts"
    total_size = get_file_size()
    part_size = total_size // NUM_PARTS
    
    for i in range(NUM_PARTS):
        start = i * part_size
        end = (start + part_size - 1) if i < NUM_PARTS - 1 else (total_size - 1)
        expected_len = end - start + 1
        part_file = temp_dir / f"part_{i:02d}.bin"
        
        current_len = part_file.stat().st_size if part_file.exists() else 0
        if current_len >= expected_len:
            print(f"[Part {i:02d}] Already complete ({current_len / (1024*1024):.1f} MB)")
            continue
            
        print(f"[Part {i:02d}] Downloading remaining {(expected_len - current_len) / (1024*1024):.1f} MB ...")
        actual_start = start + current_len
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Range": f"bytes={actual_start}-{end}"
        }
        
        req = urllib.request.Request(URL, headers=headers)
        with urllib.request.urlopen(req, timeout=60) as resp, open(part_file, "ab" if current_len > 0 else "wb") as out_f:
            while True:
                chunk = resp.read(1024 * 512)
                if not chunk:
                    break
                out_f.write(chunk)
        print(f"[Part {i:02d}] Completed!")

def merge_and_extract():
    temp_dir = INBOX_DIR / "_l22_parts"
    print(f"\n[Merge] Combining all 16 parts into {ZIP_PATH.name} ...")
    with open(ZIP_PATH, "wb") as out_f:
        for i in range(NUM_PARTS):
            pfile = temp_dir / f"part_{i:02d}.bin"
            with open(pfile, "rb") as in_f:
                while True:
                    buf = in_f.read(1024 * 1024 * 16)
                    if not buf:
                        break
                    out_f.write(buf)
            pfile.unlink()
    temp_dir.rmdir()
    print(f"[Merge] Done! File size: {ZIP_PATH.stat().st_size / (1024*1024):.2f} MB")
    
    print(f"\n[Extract] Extracting keyframes to {KEYFRAMES_DIR} ...")
    KEYFRAMES_DIR.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(ZIP_PATH, "r") as zf:
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
            if (i + 1) % 500 == 0 or i + 1 == total_files:
                print(f"\rExtracted: {i+1}/{total_files} items ({extracted} written)...", end="", flush=True)
    print(f"\n[Extract] Extraction complete! {extracted} new files written.")

def verify():
    l22_dirs = sorted([d for d in KEYFRAMES_DIR.iterdir() if d.is_dir() and d.name.startswith("L22")])
    total_imgs = sum(len(list(d.glob("*.jpg"))) for d in l22_dirs)
    print(f"\n[Verify] Found {len(l22_dirs)} L22 video directories with {total_imgs} total keyframe images.")
    for d in l22_dirs[:5]:
        print(f"  - {d.name}: {len(list(d.glob('*.jpg')))} frames")
    if len(l22_dirs) > 5:
        print(f"  ... and {len(l22_dirs) - 5} more directories.")

if __name__ == "__main__":
    finish_missing_parts()
    merge_and_extract()
    verify()
