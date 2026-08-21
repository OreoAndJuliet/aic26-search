"""Download and extract AIC 2026 preliminary competition dataset using requests."""

import os
import sys
import zipfile
import time
import requests
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

DOWNLOAD_ITEMS = [
    {
        "name": "map-keyframes-aic25-b1.zip",
        "url": "https://aic-data.ledo.io.vn/map-keyframes-aic25-b1.zip",
        "dest": REPO_ROOT / "data" / "map_keyframes"
    },
    {
        "name": "media-info-aic25-b1.zip",
        "url": "https://aic-data.ledo.io.vn/media-info-aic25-b1.zip",
        "dest": REPO_ROOT / "data" / "media_info"
    },
    {
        "name": "clip-features-32-aic25-b1.zip",
        "url": "https://aic-data.ledo.io.vn/clip-features-32-aic25-b1.zip",
        "dest": REPO_ROOT / "data" / "features"
    },
    {
        "name": "Keyframes_L21.zip",
        "url": "https://aic-data.ledo.io.vn/Keyframes_L21.zip",
        "dest": REPO_ROOT / "static" / "keyframes"
    },
    {
        "name": "objects-aic25-b1.zip",
        "url": "https://aic-data.ledo.io.vn/objects-aic25-b1.zip",
        "dest": REPO_ROOT / "data" / "objects"
    }
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}

def download_file(url: str, output_path: Path):
    print(f"Downloading {url} -> {output_path.name}...")
    start_time = time.time()
    
    with requests.get(url, headers=HEADERS, stream=True, timeout=30) as r:
        r.raise_for_status()
        total_size = int(r.headers.get('content-length', 0))
        downloaded = 0
        chunk_size = 1024 * 1024  # 1MB chunks
        
        with open(output_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=chunk_size):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        percent = int(downloaded * 100 / total_size)
                        downloaded_mb = downloaded / (1024 * 1024)
                        total_mb = total_size / (1024 * 1024)
                        speed = downloaded_mb / max(0.001, (time.time() - start_time))
                        sys.stdout.write(f"\r  [{percent:3d}%] {downloaded_mb:6.1f} MB / {total_mb:6.1f} MB ({speed:5.1f} MB/s)")
                        sys.stdout.flush()

    print("\n  Download complete!")

def extract_zip(zip_path: Path, dest_dir: Path):
    print(f"Extracting {zip_path.name} -> {dest_dir}...")
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, 'r') as z:
        # Check if entries have common prefix
        all_names = z.namelist()
        z.extractall(dest_dir)
    print(f"  Extracted {len(all_names)} entries.")

def main():
    inbox_dir = REPO_ROOT / "data" / "inbox"
    inbox_dir.mkdir(parents=True, exist_ok=True)
    
    target_names = sys.argv[1:] if len(sys.argv) > 1 else None
    items = DOWNLOAD_ITEMS
    if target_names:
        items = [it for it in DOWNLOAD_ITEMS if any(t.lower() in it["name"].lower() for t in target_names)]

    for item in items:
        zip_file = inbox_dir / item["name"]
        if not zip_file.exists():
            download_file(item["url"], zip_file)
        else:
            print(f"Archive {zip_file.name} already downloaded.")
            
        extract_zip(zip_file, item["dest"])
        
    print("\nAll requested datasets downloaded and extracted successfully!")

if __name__ == "__main__":
    main()
