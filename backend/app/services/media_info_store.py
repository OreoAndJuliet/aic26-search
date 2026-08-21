import json
from functools import lru_cache
from pathlib import Path

from app.core.config import settings


@lru_cache(maxsize=512)
def _get_media_info_cached(root_path: str, video_id: str) -> dict | None:
    root = Path(root_path)
    candidates = [
        root / "media-info" / f"{video_id}.json",
        root / f"{video_id}.json",
    ]
    for path in candidates:
        if path.is_file():
            with path.open("r", encoding="utf-8") as file:
                return json.load(file)
    return None


class MediaInfoStore:
    """Loads optional YouTube metadata JSON per video (L01_V001.json)."""

    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root or settings.MEDIA_INFO_ROOT)

    def _resolve_path(self, video_id: str) -> Path | None:
        candidates = [
            self.root / "media-info" / f"{video_id}.json",
            self.root / f"{video_id}.json",
        ]
        for path in candidates:
            if path.is_file():
                return path
        return None

    def get(self, video_id: str) -> dict | None:
        # Delegate to module-level cached function to avoid applying lru_cache to instance methods
        return _get_media_info_cached(str(self.root), video_id)

    def clear_cache(self) -> None:
        """Clear the LRU cache to prevent memory leaks."""
        _get_media_info_cached.cache_clear()  # type: ignore[attr-defined]

    def keyword_score(self, video_id: str, query: str) -> float:
        """Return 0-1 score when query terms appear in title/description/tags."""
        info = self.get(video_id)
        if not info or not query.strip():
            return 0.0

        q_clean = query.casefold().strip()
        terms = [term for term in q_clean.split() if len(term) >= 2]
        if not terms:
            return 0.0

        title = str(info.get("title", "")).casefold()
        author = str(info.get("author", "") or info.get("channelTitle", "")).casefold()
        desc = str(info.get("description", "")).casefold()
        raw_tags = info.get("keywords") or info.get("tags") or []
        tags = " ".join(str(t) for t in raw_tags).casefold() if isinstance(raw_tags, list) else ""

        # 1. Exact phrase in title or author
        if len(q_clean) >= 4:
            if q_clean in title:
                return 1.0
            if q_clean in author:
                return 0.85

        # 2. Token hits across fields with hierarchical weighting
        title_hits = sum(1 for term in terms if term in title)
        author_hits = sum(1 for term in terms if term in author)
        tag_hits = sum(1 for term in terms if term in tags)
        desc_hits = sum(1 for term in terms if term in desc)

        n_terms = len(terms)
        score = (
            0.50 * (title_hits / n_terms)
            + 0.25 * (author_hits / n_terms)
            + 0.15 * (tag_hits / n_terms)
            + 0.10 * (desc_hits / n_terms)
        )

        return min(1.0, round(score, 4))


media_info_store = MediaInfoStore()

