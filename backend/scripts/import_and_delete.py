r"""Import zip archives from an inbox, extract them, then optionally delete the original zip files.

This re-uses app.services.zip_ingest.ZipIngestService to perform the extraction safely,
then removes the processed zip files (with retries) if requested.

Usage:
  # From project root (PYTHONPATH is set automatically by the script)
  python scripts/import_and_delete.py --inbox data/inbox --delete
  
  # From scripts directory
  cd scripts
  python import_and_delete.py --inbox ../data/inbox --delete

Options:
  --inbox       Path to the inbox directory (default: data/inbox)
  --processed   Path to processed directory (default: <inbox>/processed)
  --no-delete   Extract but do not delete processed zip files (default: delete)
  --dry-run     Show what would be done without extracting or deleting

Notes:
- This script uses the project's ZipIngestService, so it honors the same safety checks and extraction rules.
- By default the ZipIngestService will move processed zip files into the processed directory; this script will then delete those processed files if --no-delete is not set.
- Be careful: deletion is permanent. Use --dry-run to verify actions first.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# Make the repository root importable when running this script directly from the shell.
# This avoids the need to set PYTHONPATH manually in the environment.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.zip_ingest import ZipIngestService


def parse_args():
    parser = argparse.ArgumentParser(description="Import zips from inbox and optionally delete originals after extraction")
    parser.add_argument("--inbox", type=Path, default=Path("data/inbox"), help="Inbox directory containing zip files")
    parser.add_argument("--processed", type=Path, default=None, help="Processed directory (defaults to <inbox>/processed)")
    parser.add_argument("--no-delete", dest="delete", action="store_false", help="Do not delete processed zip files after extraction")
    parser.add_argument("--dry-run", action="store_true", help="Show actions without performing them")
    return parser.parse_args()


def safe_remove(path: Path, attempts: int = 5, delay: float = 1.0) -> bool:
    """Attempt to remove a file with retries to tolerate transient locks."""
    for attempt in range(1, attempts + 1):
        try:
            if path.exists():
                path.unlink()
            return True
        except PermissionError:
            if attempt < attempts:
                time.sleep(delay)
                continue
            return False
        except OSError:
            return False
    return False


def main():
    args = parse_args()
    inbox = args.inbox
    processed = args.processed or (inbox / "processed")
    print(f"Inbox: {inbox}")
    print(f"Processed: {processed}")
    if args.dry_run:
        print("Dry-run mode: no files will be changed.")

    service = ZipIngestService(inbox_dir=inbox, processed_dir=processed)

    if args.dry_run:
        # Show which zips would be processed
        inbox.mkdir(parents=True, exist_ok=True)
        zips = sorted([p.name for p in inbox.iterdir() if p.is_file() and p.suffix.lower() == ".zip"])
        if not zips:
            print("No zip files found in inbox.")
            return 0
        print("Found zip files:")
        for z in zips:
            print("  ", z)
        print("After extraction the processed zip names (in the processed dir) would be:")
        for z in zips:
            print("  ", Path(z))
        return 0

    # Run ingestion
    results = service.ingest_inbox()
    if not results:
        print("No archives were processed.")
        return 0

    print(json.dumps([r.__dict__ for r in results], indent=2))

    # Delete processed zips if requested
    if args.delete:
        deleted: list[str] = []
        failed: list[str] = []
        for r in results:
            candidate = processed / r.zip_name
            if candidate.exists():
                ok = safe_remove(candidate)
                if ok:
                    deleted.append(str(candidate))
                else:
                    failed.append(str(candidate))
            else:
                # Sometimes the service may not have moved the zip (if inbox==processed), try inbox
                alt = inbox / r.zip_name
                if alt.exists():
                    ok = safe_remove(alt)
                    if ok:
                        deleted.append(str(alt))
                    else:
                        failed.append(str(alt))
                else:
                    # Nothing to delete
                    pass
        print(f"Deleted {len(deleted)} files")
        if deleted:
            for p in deleted:
                print("  ", p)
        if failed:
            print(f"Failed to delete {len(failed)} files")
            for p in failed:
                print("  ", p)

    else:
        print("Deletion skipped ( --no-delete specified ).")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
