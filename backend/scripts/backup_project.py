"""Cross-Platform Project & Database Backup Utility.

Creates fast, verified timestamped zip snapshots or folder copies of the AIC 2026 backend codebase,
models, vector indexes, gazetteers, and configuration files with SHA256 integrity.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def calculate_sha256(filepath: Path) -> str:
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def collect_project_files(
    include_static: bool = False,
    include_features: bool = False,
    include_objects: bool = False,
    include_venv: bool = False,
) -> list[tuple[Path, str]]:
    """Collect project files by explicit component inclusion for sub-second scanning."""
    files: list[tuple[Path, str]] = []
    exclude_exts = {".pyc", ".pyo", ".pyd", ".tmp", ".log", ".err"}

    # 1. Root configuration & code files
    for item in REPO_ROOT.iterdir():
        if item.is_file():
            if item.suffix.lower() not in exclude_exts and not item.name.startswith("."):
                files.append((item, item.name))
            elif item.name in {".env", ".env.example", ".gitignore"}:
                files.append((item, item.name))

    # 2. Core Python modules & tests & scripts
    for folder_name in ["app", "tests", "scripts", "submission"]:
        folder = REPO_ROOT / folder_name
        if folder.is_dir():
            for root, dirs, f_list in os.walk(folder):
                dirs[:] = [d for d in dirs if d not in {"__pycache__", ".pytest_cache", ".ruff_cache"}]
                for f in f_list:
                    p = Path(root) / f
                    if p.suffix.lower() not in exclude_exts:
                        rel = p.relative_to(REPO_ROOT).as_posix()
                        files.append((p, rel))

    # 3. Data layer (indices, metadata, csvs, gazetteers, map_keyframes, media_info)
    data_dir = REPO_ROOT / "data"
    if data_dir.is_dir():
        for item in data_dir.iterdir():
            if item.is_file():
                if item.suffix.lower() in {".json", ".csv", ".bin", ".txt", ".pkl"}:
                    files.append((item, f"data/{item.name}"))
            elif item.is_dir():
                if item.name in {"gazetteers", "map_keyframes", "media_info", "inbox"}:
                    for root, dirs, f_list in os.walk(item):
                        for f in f_list:
                            p = Path(root) / f
                            if p.suffix.lower() not in exclude_exts:
                                rel = p.relative_to(REPO_ROOT).as_posix()
                                files.append((p, rel))
                elif item.name == "features" and include_features:
                    for root, dirs, f_list in os.walk(item):
                        for f in f_list:
                            p = Path(root) / f
                            rel = p.relative_to(REPO_ROOT).as_posix()
                            files.append((p, rel))
                elif item.name == "objects" and include_objects:
                    for root, dirs, f_list in os.walk(item):
                        for f in f_list:
                            p = Path(root) / f
                            rel = p.relative_to(REPO_ROOT).as_posix()
                            files.append((p, rel))

    # 4. Optional static keyframe images
    if include_static:
        static_dir = REPO_ROOT / "static"
        if static_dir.is_dir():
            for root, dirs, f_list in os.walk(static_dir):
                for f in f_list:
                    p = Path(root) / f
                    rel = p.relative_to(REPO_ROOT).as_posix()
                    files.append((p, rel))

    return files


def create_backup(
    destination_root: Path,
    include_static: bool = False,
    include_features: bool = False,
    include_objects: bool = False,
    include_venv: bool = False,
    as_zip: bool = True,
    keep: int = 5,
) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    destination_root.mkdir(parents=True, exist_ok=True)

    files_to_backup = collect_project_files(
        include_static=include_static,
        include_features=include_features,
        include_objects=include_objects,
        include_venv=include_venv,
    )

    total_bytes = sum(f[0].stat().st_size for f in files_to_backup if f[0].is_file())
    print(f"[INFO] Discovered {len(files_to_backup)} files ({total_bytes / (1024*1024):.2f} MB) to back up.")

    manifest: dict[str, object] = {
        "timestamp": timestamp,
        "repo_root": str(REPO_ROOT),
        "total_files": len(files_to_backup),
        "total_bytes": total_bytes,
        "files": {},
    }

    if as_zip:
        archive_name = f"aic_backup_{timestamp}.zip"
        archive_path = destination_root / archive_name
        print(f"[INFO] Archiving into {archive_path}...")

        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_STORED, allowZip64=True) as zf:
            for src_path, rel_path in files_to_backup:
                zf.write(src_path, rel_path)
                manifest["files"][rel_path] = {
                    "size": src_path.stat().st_size,
                }

        # Write manifest sidecar
        manifest_path = destination_root / f"aic_backup_{timestamp}_manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as mf:
            json.dump(manifest, mf, indent=2)

        # Write SHA256 of the zip file
        zip_sha = calculate_sha256(archive_path)
        sha_file = destination_root / f"{archive_name}.sha256"
        sha_file.write_text(f"{zip_sha}  {archive_name}\n", encoding="ascii")

        print(f"[SUCCESS] Archive created: {archive_path} ({archive_path.stat().st_size / (1024*1024):.2f} MB)")
        target_output = archive_path
    else:
        folder_name = f"aic_snapshot_{timestamp}"
        folder_path = destination_root / folder_name
        folder_path.mkdir(parents=True, exist_ok=True)
        print(f"[INFO] Copying files to {folder_path}...")

        for src_path, rel_path in files_to_backup:
            dest = folder_path / rel_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_path, dest)
            manifest["files"][rel_path] = {
                "size": src_path.stat().st_size,
            }

        manifest_path = folder_path / "backup_manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as mf:
            json.dump(manifest, mf, indent=2)

        print(f"[SUCCESS] Snapshot folder created: {folder_path}")
        target_output = folder_path

    # Apply Retention Policy
    if keep > 0:
        existing_zips = sorted(
            destination_root.glob("aic_backup_*.zip"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if len(existing_zips) > keep:
            for old_zip in existing_zips[keep:]:
                print(f"[INFO] Removing old backup: {old_zip.name}")
                try:
                    old_zip.unlink(missing_ok=True)
                    (destination_root / f"{old_zip.name}.sha256").unlink(missing_ok=True)
                    (destination_root / f"{old_zip.stem}_manifest.json").unlink(missing_ok=True)
                except Exception as exc:
                    print(f"[WARN] Failed to remove {old_zip.name}: {exc}")

    return target_output


def main() -> None:
    parser = argparse.ArgumentParser(description="AIC 2026 Project Backup Utility")
    parser.add_argument(
        "--destination",
        "-d",
        type=Path,
        default=REPO_ROOT / "backups",
        help="Destination directory for backups (default: ./backups)",
    )
    parser.add_argument("--include-static", action="store_true", help="Include static keyframe images")
    parser.add_argument("--include-features", action="store_true", help="Include data/features .npy files")
    parser.add_argument("--include-objects", action="store_true", help="Include data/objects JSON files")
    parser.add_argument("--folder", action="store_true", help="Create uncompressed folder copy instead of ZIP")
    parser.add_argument("--keep", type=int, default=5, help="Number of backups to retain (default: 5)")
    args = parser.parse_args()

    started = time.perf_counter()
    output = create_backup(
        destination_root=args.destination,
        include_static=args.include_static,
        include_features=args.include_features,
        include_objects=args.include_objects,
        as_zip=not args.folder,
        keep=args.keep,
    )
    elapsed = time.perf_counter() - started
    print(f"[INFO] Backup completed in {elapsed:.2f} seconds -> {output}")


if __name__ == "__main__":
    main()
