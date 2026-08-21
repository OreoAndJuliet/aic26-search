"""Extract keyframes and videos from processed zip files to static directories."""

import shutil
import sys
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from app.core.config import settings
from app.services.zip_ingest import ZipIngestService


def main():
    inbox_dir = Path(settings.ZIP_INBOX_DIR)
    processed_dir = inbox_dir / "processed"
    
    print(f"Inbox directory: {inbox_dir}")
    print(f"Processed directory: {processed_dir}")
    
    # Move zips from processed back to inbox
    if processed_dir.exists():
        zip_files = list(processed_dir.glob("*.zip"))
        print(f"Found {len(zip_files)} zip files in processed directory")
        
        for zip_file in zip_files:
            print(f"Moving {zip_file.name} back to inbox...")
            destination = inbox_dir / zip_file.name
            if destination.exists():
                destination.unlink()
            shutil.move(str(zip_file), str(destination))
            print(f"  Moved to {destination}")
    else:
        print("No processed directory found")
    
    # Run zip ingest service
    print("\nRunning zip ingest service...")
    service = ZipIngestService()
    results = service.ingest_inbox()
    
    print(f"\nExtracted {len(results)} zip files:")
    for result in results:
        print(f"  {result.zip_name}: {result.target} ({result.files_written} written, {result.skipped_existing} skipped)")
    
    print("\nExtraction complete!")
    print(f"Keyframes directory: {settings.KEYFRAMES_DIR}")
    print(f"Videos directory: {settings.VIDEOS_DIR}")

if __name__ == "__main__":
    main()
