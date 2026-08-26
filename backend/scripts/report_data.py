import os
from pathlib import Path
from collections import defaultdict

BACKEND_DIR = Path(__file__).parent.parent
KEYFRAMES_DIR = BACKEND_DIR / "static" / "keyframes"
VIDEOS_DIR = BACKEND_DIR / "data" / "videos"

def get_grouped_folders(parent_dir):
    if not parent_dir.exists():
        return {}
    groups = defaultdict(list)
    for folder in parent_dir.iterdir():
        if folder.is_dir():
            name = folder.name
            if "_" in name:
                group = name.split("_")[0]
                groups[group].append(name)
            else:
                groups[name].append(name)
    return {k: len(v) for k, v in sorted(groups.items())}

def get_videos():
    if not VIDEOS_DIR.exists():
        return {}
    groups = defaultdict(int)
    for f in VIDEOS_DIR.iterdir():
        if f.is_file() and (f.name.endswith(".mp4") or f.name.endswith(".mkv")):
            if "_" in f.name:
                group = f.name.split("_")[0]
                groups[group] += 1
    return dict(sorted(groups.items()))

kf = get_grouped_folders(KEYFRAMES_DIR)
vid = get_videos()

print("=== DATA REPORT ===")
print("Keyframes (Extracted Folders):")
for k, v in kf.items():
    print(f"  - {k}: {v} folders")
print("\nVideos (.mp4 files):")
for k, v in vid.items():
    print(f"  - {k}: {v} videos")
