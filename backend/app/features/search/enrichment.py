"""Optional result enrichment for search responses."""

from __future__ import annotations

from app.core.config import settings
from app.services.media_info_store import media_info_store


def attach_media_info(results: list[dict]) -> list[dict]:
    """Attach YouTube metadata fields when media-info JSON is available."""
    if not settings.KIS_MEDIA_INFO_ENRICH_ENABLED:
        return results

    enriched: list[dict] = []
    for item in results:
        copy = dict(item)
        info = media_info_store.get(str(copy["video_id"]))
        if info:
            copy["media_title"] = info.get("title")
            copy["media_channel"] = info.get("author") or info.get("channelTitle")
            copy["media_description"] = info.get("description")
        enriched.append(copy)
    return enriched
