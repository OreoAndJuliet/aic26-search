import csv
import os
import glob
from pathlib import Path
from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["preview"])

SUBMISSION_DIR = Path("data/submission")
MAP_KEYFRAMES_DIR = Path("data/map_keyframes")
STATIC_KEYFRAMES_DIR = Path("static/keyframes")

def get_keyframe_name(video_id: str, target_frame_idx: str) -> str | None:
    map_file = MAP_KEYFRAMES_DIR / f"{video_id}.csv"
    if map_file.exists():
        with open(map_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('frame_idx') == target_frame_idx:
                    return f"{int(row['n']):03d}.jpg"
    return None

@router.get("/preview")
async def list_submissions():
    if not SUBMISSION_DIR.exists():
        return {"status": "success", "files": []}
    
    csv_files = glob.glob(str(SUBMISSION_DIR / "*.csv"))
    files = [Path(f).name for f in csv_files]
    return {"status": "success", "files": sorted(files)}

@router.get("/preview/{filename}")
async def get_submission_preview(filename: str):
    file_path = SUBMISSION_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
        
    is_qa = '-qa' in filename.lower()
    items = []
    
    with open(file_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        for row_idx, row in enumerate(reader):
            if not row or len(row) < 2:
                continue
                
            video_id = row[0].strip()
            frames = row[1:]
            
            qa_answer = ""
            if is_qa and len(frames) >= 2:
                frame_ids = [frames[0].strip()]
                qa_answer = frames[1].strip()
            else:
                frame_ids = [f.strip() for f in frames if f.strip().isdigit()]
                
            for frame_id in frame_ids:
                img_name = get_keyframe_name(video_id, frame_id)
                if not img_name:
                    try:
                        img_name = f"{int(frame_id):03d}.jpg"
                    except ValueError:
                        img_name = f"{frame_id}.jpg"
                
                # Check if file actually exists
                img_path = STATIC_KEYFRAMES_DIR / video_id / img_name
                
                items.append({
                    "id": f"{video_id}-{frame_id}-{row_idx}-{len(items)}",
                    "video_id": video_id,
                    "frame_id": frame_id,
                    "img_url": f"/keyframes/{video_id}/{img_name}",
                    "is_missing": not img_path.exists(),
                    "answer": qa_answer
                })
                
    return {
        "status": "success",
        "filename": filename,
        "type": "qa" if is_qa else ("trake" if "-trake" in filename.lower() else "kis"),
        "items": items
    }
