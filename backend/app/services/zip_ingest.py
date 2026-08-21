"""Extract AIC organizer zip bundles from an inbox folder into static/."""

from __future__ import annotations

import logging
import re
import shutil
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from app.core.config import settings

logger = logging.getLogger(__name__)

KEYFRAMES_PREFIX = PurePosixPath("keyframes")
VIDEO_PREFIXES = (PurePosixPath("video"), PurePosixPath("videos"))


@dataclass(frozen=True)
class ZipIngestResult:
    zip_name: str
    target: str
    files_written: int
    skipped_existing: int


class ZipIngestService:
    """Scan inbox for zip files and extract keyframes/videos into static/."""

    def __init__(
        self,
        *,
        inbox_dir: Path | None = None,
        keyframes_dir: Path | None = None,
        videos_dir: Path | None = None,
        processed_dir: Path | None = None,
    ) -> None:
        self.inbox_dir = Path(inbox_dir or settings.ZIP_INBOX_DIR)
        self.keyframes_dir = Path(keyframes_dir or settings.KEYFRAMES_DIR)
        self.videos_dir = Path(videos_dir or settings.VIDEOS_DIR)
        self.processed_dir = Path(processed_dir or (self.inbox_dir / "processed"))

    def ingest_inbox(self) -> list[ZipIngestResult]:
        """Process every *.zip in the inbox; move successful archives to processed/."""
        self.inbox_dir.mkdir(parents=True, exist_ok=True)
        self.keyframes_dir.mkdir(parents=True, exist_ok=True)
        self.videos_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)

        results: list[ZipIngestResult] = []
        zip_paths = sorted(
            path
            for path in self.inbox_dir.iterdir()
            if path.is_file() and path.suffix.lower() == ".zip"
        )

        if not zip_paths:
            logger.info("zip_ingest inbox=%s no zip files found", self.inbox_dir)
            return results

        for zip_path in zip_paths:
            try:
                result = self._ingest_zip(zip_path)
            except (zipfile.BadZipFile, OSError) as exc:
                logger.warning("zip_ingest failed zip=%s: %s", zip_path.name, exc)
                continue

            if result is None:
                logger.warning("zip_ingest skipped zip=%s (unknown layout or empty)", zip_path.name)
                continue

            self._move_to_processed(zip_path)
            results.append(result)
            logger.info(
                "zip_ingest zip=%s target=%s written=%s skipped=%s",
                result.zip_name,
                result.target,
                result.files_written,
                result.skipped_existing,
            )

        return results

    def _ingest_zip(self, zip_path: Path) -> ZipIngestResult | None:
        with zipfile.ZipFile(zip_path) as archive:
            members = [name for name in archive.namelist() if not name.endswith("/")]
            if not members:
                return None

            target = self._detect_target(zip_path.name, members)
            if target == "keyframes":
                written, skipped = self._extract_keyframes(archive, members)
                return ZipIngestResult(zip_path.name, "keyframes", written, skipped)
            if target == "videos":
                written, skipped = self._extract_videos(archive, members)
                return ZipIngestResult(zip_path.name, "videos", written, skipped)
            return None

    def _detect_target(self, zip_name: str, members: list[str]) -> str | None:
        lowered = zip_name.casefold()
        if "keyframe" in lowered:
            return "keyframes"
        if re.search(r"\bvideos?\b", lowered):
            return "videos"

        for member in members:
            parts = PurePosixPath(member).parts
            if not parts:
                continue
            root = PurePosixPath(parts[0])
            if root == KEYFRAMES_PREFIX:
                return "keyframes"
            if root in VIDEO_PREFIXES:
                return "videos"
        return None

    def _extract_keyframes(
        self,
        archive: zipfile.ZipFile,
        members: list[str],
    ) -> tuple[int, int]:
        written = 0
        skipped = 0
        for member in members:
            relative = self._relative_under_prefix(member, KEYFRAMES_PREFIX)
            if relative is None:
                continue
            destination = self._safe_destination(self.keyframes_dir, relative)
            if destination is None:
                logger.warning("zip_ingest rejected unsafe keyframe path member=%s", member)
                continue
            if destination.is_file():
                skipped += 1
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            try:
                with archive.open(member) as source, destination.open("wb") as target:
                    shutil.copyfileobj(source, target)
                written += 1
            except OSError as exc:
                logger.warning("zip_ingest failed to extract keyframe member=%s error=%s", member, exc)
                if destination.exists():
                    destination.unlink()
                continue
        return written, skipped

    def _extract_videos(
        self,
        archive: zipfile.ZipFile,
        members: list[str],
    ) -> tuple[int, int]:
        written = 0
        skipped = 0
        for member in members:
            relative = None
            for prefix in VIDEO_PREFIXES:
                relative = self._relative_under_prefix(member, prefix)
                if relative is not None:
                    break
            if relative is None or len(relative.parts) != 1:
                continue
            destination = self._safe_destination(self.videos_dir, relative)
            if destination is None:
                logger.warning("zip_ingest rejected unsafe video path member=%s", member)
                continue
            if destination.is_file():
                skipped += 1
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            try:
                with archive.open(member) as source, destination.open("wb") as target:
                    shutil.copyfileobj(source, target)
                written += 1
            except OSError as exc:
                logger.warning("zip_ingest failed to extract video member=%s error=%s", member, exc)
                if destination.exists():
                    destination.unlink()
                continue
        return written, skipped

    @staticmethod
    def _relative_under_prefix(member: str, prefix: PurePosixPath) -> PurePosixPath | None:
        parts = PurePosixPath(member).parts
        if len(parts) < 2 or PurePosixPath(parts[0]) != prefix:
            return None
        return PurePosixPath(*parts[1:])

    @staticmethod
    def _safe_destination(root: Path, relative: PurePosixPath) -> Path | None:
        destination = (root / Path(*relative.parts)).resolve()
        root_resolved = root.resolve()
        try:
            destination.relative_to(root_resolved)
        except ValueError:
            return None
        if ".." in relative.parts:
            return None
        return destination

    def _move_to_processed(self, zip_path: Path) -> None:
        destination = self.processed_dir / zip_path.name
        # If an older processed file exists, remove it first (ignore failures)
        try:
            if destination.exists():
                destination.unlink()
        except OSError as exc:
            logger.warning("zip_ingest could not remove existing processed file=%s: %s", destination, exc)

        # Attempt to move the file with retries to tolerate transient Windows file locks
        attempts = 5
        for attempt in range(1, attempts + 1):
            try:
                shutil.move(str(zip_path), str(destination))
                return
            except PermissionError as exc:
                # File is likely held open by another process (antivirus, indexer, explorer). Retry.
                logger.warning(
                    "zip_ingest move attempt %d/%d failed due to file lock on %s: %s",
                    attempt,
                    attempts,
                    zip_path.name,
                    exc,
                )
                if attempt < attempts:
                    # Use synchronous sleep - this is not an async context
                    time.sleep(1)
                    continue
                else:
                    logger.error("zip_ingest could not move zip to processed after %d attempts: %s", attempts, zip_path.name)
                    return
            except OSError:
                logger.exception("zip_ingest unexpected error while moving zip=%s to processed", zip_path.name)
                return


zip_ingest_service = ZipIngestService()
