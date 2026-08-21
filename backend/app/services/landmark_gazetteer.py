"""Vietnam Landmarks & Cultural Gazetteer for KIS / VQA Grounding."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)


class VietnamLandmarkGazetteer:
    def __init__(self, database_path: Path | None = None) -> None:
        self.database_path = database_path or (settings.DATA_DIR / "vietnam_landmarks.json")
        self._landmarks: list[dict[str, Any]] = []
        self._lookup_map: dict[str, dict[str, Any]] = {}
        self._is_loaded = False

    def load(self) -> None:
        """Load and index Vietnamese landmarks from JSON gazetteer."""
        if not self.database_path.is_file():
            logger.debug("Landmark database %s not found.", self.database_path)
            return

        try:
            data = json.loads(self.database_path.read_text(encoding="utf-8"))
            self._landmarks = data if isinstance(data, list) else []

            for lm in self._landmarks:
                name = lm.get("name", "").lower()
                self._lookup_map[name] = lm

                for alias in lm.get("aliases", []):
                    self._lookup_map[alias.lower()] = lm

                canon_en = lm.get("canonical_en", "").lower()
                if canon_en:
                    self._lookup_map[canon_en] = lm

            self._is_loaded = True
            logger.info("Loaded %d Vietnamese landmarks into gazetteer.", len(self._landmarks))
        except Exception as exc:
            logger.warning("Failed loading landmark gazetteer %s: %s", self.database_path, exc)

    def match_landmarks(self, query: str) -> list[dict[str, Any]]:
        """Identify if any famous Vietnamese landmark is mentioned in the query."""
        if not self._is_loaded:
            self.load()

        matched: list[dict[str, Any]] = []
        q_lower = query.lower()

        # Sort lookup keys by descending length to match longest phrases first
        for key, lm in sorted(self._lookup_map.items(), key=lambda x: len(x[0]), reverse=True):
            if re.search(r"\b" + re.escape(key) + r"\b", q_lower):
                if lm not in matched:
                    matched.append(lm)

        return matched

    def enrich_query_with_landmarks(self, query: str) -> str:
        """Enrich query with canonical English & visual synonyms if a Vietnamese landmark is present."""
        matched = self.match_landmarks(query)
        if not matched:
            return query

        additions = []
        for lm in matched:
            canon = lm.get("canonical_en", "")
            if canon.lower() not in query.lower():
                additions.append(canon)

        if additions:
            return f"{query} ({', '.join(additions)})"
        return query


landmark_gazetteer = VietnamLandmarkGazetteer()
