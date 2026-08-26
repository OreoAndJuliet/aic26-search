import zipfile
from pathlib import Path
import sys

BACKEND_DIR = Path(__file__).resolve().parent.parent
KEYFRAMES_DIR = BACKEND_DIR / "static" / "keyframes"
ZIP_PATH = BACKEND_DIR.parent / "Keyframes_L24.zip"

def extract_l24():
    if not ZIP_PATH.exists():
        print(f"File not found: {ZIP_PATH}")
        sys.exit(1)
        
    print(f"\nExtracting {ZIP_PATH.name} to {KEYFRAMES_DIR}...")
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
            if (i + 1) % 1000 == 0 or i + 1 == total_files:
                print(f"\rExtracted: {i+1}/{total_files} items ({extracted} written)...", end="", flush=True)
    print(f"\nExtraction finished for L24! Total new files written: {extracted}")

if __name__ == "__main__":
    extract_l24()
