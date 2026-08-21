"""Local Inverted Keyword & Text Grounding Store for KIS queries."""

from __future__ import annotations

import csv
import json
import logging
import re
import unicodedata
from pathlib import Path
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)


def _strip_accents(text: str) -> str:
    """Remove Vietnamese diacritics for robust accent-insensitive matching."""
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return text.replace("đ", "d").replace("Đ", "D")


class OCRTextStore:
    def __init__(
        self,
        media_info_dir: Path | None = None,
        ocr_csv_path: Path | None = None,
        ocr_txt_path: Path | None = None,
    ) -> None:
        self.media_info_dir = media_info_dir or (settings.DATA_DIR / "media_info")
        self.ocr_csv_path = ocr_csv_path or (settings.DATA_DIR / "ocr_database.csv")
        self.ocr_txt_path = ocr_txt_path or (settings.DATA_DIR / "ocr_database.txt")
        self._inverted_index: dict[str, set[str]] = {}
        self._video_text_cache: dict[str, str] = {}
        self._frame_ocr_entries: dict[tuple[str, int], dict[str, Any]] = {}
        self._is_indexed = False

    def build_index(self) -> None:
        """Scan media-info JSON files and OCR database (CSV/TXT) to build in-memory index."""
        # 1. Load from structured OCR CSV database
        if self.ocr_csv_path.is_file():
            try:
                with open(self.ocr_csv_path, mode="r", encoding="utf-8", errors="ignore") as fh:
                    reader = csv.DictReader(fh)
                    for row in reader:
                        v_id = str(row.get("video_id", "")).strip()
                        f_id_str = str(row.get("frame_id", "0")).strip()
                        f_id = int(f_id_str) if f_id_str.isdigit() else 0
                        ts_str = str(row.get("timestamp", "0.0")).strip()
                        ts = float(ts_str) if ts_str.replace(".", "", 1).isdigit() else 0.0
                        conf_str = str(row.get("confidence", "0.9")).strip()
                        conf = float(conf_str) if conf_str.replace(".", "", 1).isdigit() else 0.9
                        detected_text = str(row.get("detected_text", "")).strip()

                        if v_id and detected_text:
                            curr_text = self._video_text_cache.get(v_id, "")
                            self._video_text_cache[v_id] = f"{curr_text} {detected_text}".lower()
                            self._frame_ocr_entries[(v_id, f_id)] = {
                                "video_id": v_id,
                                "frame_id": f_id,
                                "timestamp": ts,
                                "confidence": conf,
                                "detected_text": detected_text,
                                "bbox_norm": row.get("bbox_norm", ""),
                            }

                            for tok in re.findall(r"\b[a-zA-Z0-9_\-À-ỹ]{2,}\b", detected_text.lower()):
                                if tok not in self._inverted_index:
                                    self._inverted_index[tok] = set()
                                self._inverted_index[tok].add(v_id)
            except Exception as exc:
                logger.warning("Failed reading OCR CSV database %s: %s", self.ocr_csv_path, exc)

        # 2. Load from media-info JSON files
        if self.media_info_dir.is_dir():
            json_files = list(self.media_info_dir.glob("*.json"))
            for p in json_files:
                try:
                    data = json.loads(p.read_text(encoding="utf-8", errors="ignore"))
                    video_id = p.stem
                    title = str(data.get("title", ""))
                    description = str(data.get("description", ""))
                    tags = " ".join(data.get("tags", [])) if isinstance(data.get("tags"), list) else ""
                    full_text = f"{title} {description} {tags}".lower()
                    
                    curr = self._video_text_cache.get(video_id, "")
                    self._video_text_cache[video_id] = f"{curr} {full_text}".strip()

                    tokens = re.findall(r"\b[a-zA-Z0-9_\-À-ỹ]{2,}\b", full_text)
                    for t in tokens:
                        if t not in self._inverted_index:
                            self._inverted_index[t] = set()
                        self._inverted_index[t].add(video_id)
                except Exception as exc:
                    logger.debug("Failed reading media info %s: %s", p, exc)

        self._is_indexed = True
        logger.info(
            "OCR/Text store indexed %d videos, %d frame entries, and %d distinct tokens.",
            len(self._video_text_cache),
            len(self._frame_ocr_entries),
            len(self._inverted_index),
        )

    def search_matching_frames(self, query: str, top_k: int = 10) -> list[dict[str, Any]]:
        """Search exact OCR frame matches for entities, brands, numbers, or sign texts in query."""
        if not self._is_indexed:
            self.build_index()

        q_clean = query.lower().strip()
        q_no_acc = _strip_accents(q_clean)
        
        # Stop words to ignore during OCR token search
        stop_words = {
            "trên", "duoi", "trong", "ngoai", "duong", "pho", "nguoi", "xe", "co", "nhieu", 
            "the", "a", "an", "on", "in", "at", "with", "and", "of", "scene", "street", "road"
        }

        # Tokenize query into 3+ char words
        q_tokens = [w for w in re.findall(r"\b[a-zA-Z0-9_\-À-ỹ]{3,}\b", q_clean) if w not in stop_words]
        q_tokens_no_acc = [w for w in re.findall(r"\b[a-zA-Z0-9_\-]{3,}\b", q_no_acc) if w not in stop_words]

        # Numbers & codes (e.g. 150, 24, 302, 115)
        codes = re.findall(r"\b\d+\b", q_clean)

        matched_frames: list[dict[str, Any]] = []

        for (v_id, f_id), entry in self._frame_ocr_entries.items():
            det_text = str(entry.get("detected_text", "")).lower()
            det_no_acc = _strip_accents(det_text)
            conf = float(entry.get("confidence", 0.9))
            ts = float(entry.get("timestamp", 0.0))

            match_score = 0.0
            matched_terms = []

            # 1. Exact phrase/substring match
            for phrase in [q_clean, q_no_acc]:
                if len(phrase) >= 5 and (phrase in det_text or phrase in det_no_acc or det_text in phrase or det_no_acc in phrase):
                    match_score = max(match_score, 0.98 * conf)
                    matched_terms.append(det_text)

            # 2. Token matches
            for tok, tok_na in zip(q_tokens, q_tokens_no_acc):
                if tok in det_text or tok_na in det_no_acc:
                    match_score = max(match_score, 0.92 * conf)
                    matched_terms.append(tok)

            # 3. Number/code matches (e.g., bus "150", room "302")
            for c in codes:
                if c in det_text or c in det_no_acc:
                    match_score = max(match_score, 0.90 * conf)
                    matched_terms.append(f"code_{c}")

            if match_score > 0.0:
                matched_frames.append({
                    "video_id": v_id,
                    "frame_id": f_id,
                    "keyframe_id": f_id,
                    "timestamp": ts,
                    "score": round(match_score, 4),
                    "r_score": round(match_score, 4),
                    "detected_text": entry.get("detected_text", ""),
                    "matched_terms": matched_terms,
                    "source": "ocr_inverted_index"
                })

        # Sort by score descending
        matched_frames.sort(key=lambda x: x["score"], reverse=True)
        return matched_frames[:top_k]

    def extract_text_query_terms(self, query: str) -> list[str]:
        """Extract high-information alphanumeric tokens, numbers, landmarks, and quoted phrases from query."""
        terms: list[str] = []
        # Quoted terms
        quotes = re.findall(r"['\"]([^'\"]+)['\"]", query)
        for q in quotes:
            terms.extend(re.findall(r"\b[a-zA-Z0-9À-ỹ]+\b", q.lower()))

        # Numbers and codes (e.g. 150, L22, V021)
        codes = re.findall(r"\b\d+\b|\b[a-zA-Z]+\d+\b", query.lower())
        terms.extend(codes)

        # General words (len >= 3)
        words = re.findall(r"\b[a-zA-Z0-9À-ỹ]{3,}\b", query.lower())
        terms.extend(words)

        # Landmark tokens
        try:
            from app.services.landmark_gazetteer import landmark_gazetteer
            matched_lms = landmark_gazetteer.match_landmarks(query)
            for lm in matched_lms:
                terms.extend(re.findall(r"\b[a-zA-Z0-9À-ỹ]+\b", lm.get("name", "").lower()))
                terms.extend(re.findall(r"\b[a-zA-Z0-9À-ỹ]+\b", lm.get("canonical_en", "").lower()))
        except Exception as exc:
            logger.debug("Landmark extraction in OCR store failed: %s", exc)

        return list(set(terms))

    def score_video(self, video_id: str, query_terms: list[str]) -> float:
        """Calculate normalized BM25-like overlap score for a video."""
        if not self._is_indexed:
            self.build_index()

        text = self._video_text_cache.get(video_id, "")
        if not text or not query_terms:
            return 0.0

        matches = sum(1 for t in query_terms if t in text)
        return float(matches / len(query_terms)) if query_terms else 0.0

    def get_frame_ocr(self, video_id: str, frame_id: int) -> str:
        """Retrieve detected OCR text for a specific keyframe."""
        entry = self._frame_ocr_entries.get((video_id, frame_id))
        if entry is not None:
            return entry.get("detected_text", "")
        if not self._is_indexed:
            self.build_index()
        entry = self._frame_ocr_entries.get((video_id, frame_id))
        return entry.get("detected_text", "") if entry else ""

    def get_frame_ocr_text(self, video_id: str, frame_id: int) -> str:
        """Alias for get_frame_ocr."""
        return self.get_frame_ocr(video_id, frame_id)


ocr_store = OCRTextStore()
