"""In-Memory MediaInfo BM25 Inverted Store for AIC 2026.

Parses organizer-provided media_info/*.json and data/metadata.json files
into a high-speed token-inverted index with BM25 term weighting (0ms local search).
"""

from __future__ import annotations

import json
import logging
import math
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)


def _normalize_text(text: str) -> str:
    """Normalize Vietnamese / English text, remove accents and punctuation for indexing."""
    if not text:
        return ""
    text = text.lower()
    # Normalize unicode
    text = unicodedata.normalize("NFD", text)
    # Remove accents for robust unaccented matching
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _tokenize(text: str) -> list[str]:
    """Tokenize normalized text into word tokens."""
    norm = _normalize_text(text)
    return [t for t in norm.split() if len(t) > 1]


class MediaInfoStore:
    """In-memory BM25 inverted index over video titles, channel names, descriptions, and tags."""

    def __init__(self, media_info_dir: Path | None = None, metadata_path: Path | None = None) -> None:
        self.media_info_dir = media_info_dir or Path(settings.DATA_DIR) / "media_info"
        self.metadata_path = metadata_path or Path(settings.METADATA_PATH)
        self._doc_tokens: dict[str, list[str]] = {}  # video_id -> tokens
        self._doc_lengths: dict[str, int] = {}  # video_id -> length
        self._inverted_index: dict[str, dict[str, int]] = defaultdict(dict)  # token -> {video_id: tf}
        self._df: dict[str, int] = defaultdict(int)  # token -> doc_freq
        self._video_metadata: dict[str, dict[str, Any]] = {}  # video_id -> raw info
        self._avg_dl: float = 1.0
        self._total_docs: int = 0
        self._is_indexed: bool = False

    def build_index(self, force: bool = False) -> int:
        """Scan media_info directory and build BM25 inverted index."""
        if self._is_indexed and not force:
            return self._total_docs

        self._doc_tokens.clear()
        self._doc_lengths.clear()
        self._inverted_index.clear()
        self._df.clear()
        self._video_metadata.clear()

        # 1. Ingest media_info JSONs
        if self.media_info_dir.is_dir():
            for json_file in self.media_info_dir.glob("*.json"):
                v_id = json_file.stem
                try:
                    with open(json_file, "r", encoding="utf-8", errors="ignore") as f:
                        data = json.load(f)
                    self._video_metadata[v_id] = data
                    title = str(data.get("title", ""))
                    desc = str(data.get("description", ""))
                    chan = str(data.get("channel", data.get("uploader", "")))
                    tags = " ".join(data.get("tags", [])) if isinstance(data.get("tags"), list) else str(data.get("tags", ""))
                    combined_text = f"{title} {chan} {tags} {desc[:500]}"
                    tokens = _tokenize(combined_text)
                    self._doc_tokens[v_id] = tokens
                except Exception as exc:
                    logger.debug("Failed parsing media_info for %s: %s", v_id, exc)

        # 2. Ingest metadata.json as fallback / supplement
        if self.metadata_path.is_file():
            try:
                with open(self.metadata_path, "r", encoding="utf-8", errors="ignore") as f:
                    meta_data = json.load(f)
                if isinstance(meta_data, dict):
                    for v_id, info in meta_data.items():
                        if v_id not in self._doc_tokens and isinstance(info, dict):
                            title = str(info.get("title", ""))
                            chan = str(info.get("channel", ""))
                            desc = str(info.get("description", ""))
                            tokens = _tokenize(f"{title} {chan} {desc[:500]}")
                            if tokens:
                                self._doc_tokens[v_id] = tokens
                                self._video_metadata[v_id] = info
                elif isinstance(meta_data, list):
                    for item in meta_data:
                        if isinstance(item, dict):
                            v_id = str(item.get("video_id", "")).strip()
                            if v_id and v_id not in self._doc_tokens:
                                title = str(item.get("title", ""))
                                chan = str(item.get("channel", ""))
                                desc = str(item.get("description", ""))
                                tags = " ".join(item.get("tags", [])) if isinstance(item.get("tags"), list) else str(item.get("tags", ""))
                                tokens = _tokenize(f"{title} {chan} {tags} {desc[:500]}")
                                if tokens:
                                    self._doc_tokens[v_id] = tokens
                                    self._video_metadata[v_id] = item
            except Exception as exc:
                logger.debug("Failed parsing metadata.json: %s", exc)

        self._total_docs = len(self._doc_tokens)
        if self._total_docs == 0:
            logger.info("MediaInfoStore: No video metadata found to index.")
            self._is_indexed = True
            return 0

        # Build term frequencies and document frequencies
        total_len = 0
        for v_id, tokens in self._doc_tokens.items():
            dl = len(tokens)
            self._doc_lengths[v_id] = dl
            total_len += dl

            tf_counts: dict[str, int] = defaultdict(int)
            for t in tokens:
                tf_counts[t] += 1

            for t, count in tf_counts.items():
                self._inverted_index[t][v_id] = count
                self._df[t] += 1

        self._avg_dl = max(1.0, total_len / float(self._total_docs))
        self._is_indexed = True
        logger.info(
            "MediaInfoStore: Indexed %d videos with %d unique terms (avg_dl=%.1f).",
            self._total_docs,
            len(self._inverted_index),
            self._avg_dl,
        )
        return self._total_docs

    def search_bm25(
        self,
        query: str,
        top_k: int = 50,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> list[tuple[str, float]]:
        """Search media metadata using BM25 and return ranked list of (video_id, score)."""
        if not self._is_indexed:
            self.build_index()

        q_tokens = _tokenize(query)
        if not q_tokens or self._total_docs == 0:
            return []

        scores: dict[str, float] = defaultdict(float)
        n_docs = float(self._total_docs)

        for token in q_tokens:
            if token not in self._inverted_index:
                continue

            df = float(self._df[token])
            # Robertson-Spärck Jones IDF
            idf = math.log(1.0 + (n_docs - df + 0.5) / (df + 0.5))

            postings = self._inverted_index[token]
            for v_id, tf in postings.items():
                dl = float(self._doc_lengths.get(v_id, self._avg_dl))
                tf_norm = (tf * (k1 + 1.0)) / (tf + k1 * (1.0 - b + b * (dl / self._avg_dl)))
                scores[v_id] += idf * tf_norm

        if not scores:
            return []

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return ranked[:top_k]

    def get_metadata(self, video_id: str) -> dict[str, Any]:
        """Return cached raw metadata dictionary for a video."""
        return self._video_metadata.get(video_id, {})


# Global singleton
mediainfo_store = MediaInfoStore()
