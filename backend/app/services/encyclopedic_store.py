"""Unified Encyclopedic Vision-Language Knowledge Base for AIC 2026.

Integrates:
1. Vietnam Landmarks & Cultural Gazetteer
2. Vietnamese QCVN 41:2019 Traffic Signs
3. Commercial Brands, Retail, F&B, Logistics & Banks
4. Vehicle Types, Models & Public Transport Lines
"""

from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)


class EncyclopedicStore:
    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = data_dir or settings.DATA_DIR
        self._entity_lookup: dict[str, dict[str, Any]] = {}
        self._traffic_signs: list[dict[str, Any]] = []
        self._brands: list[dict[str, Any]] = []
        self._vehicles: list[dict[str, Any]] = []
        self._landmarks: list[dict[str, Any]] = []
        self._is_loaded = False

    @staticmethod
    @lru_cache(maxsize=4096)
    def _get_phrase_pattern(phrase: str) -> re.Pattern:
        """Return a compiled word-boundary regex for phrase. Cached to avoid recompilation."""
        return re.compile(r"\b" + re.escape(phrase) + r"\b")

    def load_all(self) -> None:
        """Load and index all structured knowledge catalogs into an ultra-fast in-memory entity graph."""
        # 1. Landmarks
        lm_path = self.data_dir / "vietnam_landmarks.json"
        if lm_path.is_file():
            try:
                self._landmarks = json.loads(lm_path.read_text(encoding="utf-8"))
                for item in self._landmarks:
                    self._register_entity(item.get("name", ""), item, "Landmark")
                    self._register_entity(item.get("canonical_en", ""), item, "Landmark")
                    for alias in item.get("aliases", []):
                        self._register_entity(alias, item, "Landmark")
            except Exception as exc:
                logger.debug("Failed loading landmarks: %s", exc)

        # 2. Traffic Signs
        signs_path = self.data_dir / "traffic_signs_vietnam.json"
        if signs_path.is_file():
            try:
                self._traffic_signs = json.loads(signs_path.read_text(encoding="utf-8"))
                for item in self._traffic_signs:
                    self._register_entity(item.get("name_vi", ""), item, "TrafficSign")
                    self._register_entity(item.get("name_en", ""), item, "TrafficSign")
                    self._register_entity(item.get("code", ""), item, "TrafficSign")
                    for cue in item.get("visual_cues", []):
                        self._register_entity(cue, item, "TrafficSign")
            except Exception as exc:
                logger.debug("Failed loading traffic signs: %s", exc)

        # 3. Brands & Retail
        brands_path = self.data_dir / "brands_and_retail.json"
        if brands_path.is_file():
            try:
                self._brands = json.loads(brands_path.read_text(encoding="utf-8"))
                for item in self._brands:
                    self._register_entity(item.get("brand", ""), item, "Brand")
                    for alias in item.get("aliases", []):
                        self._register_entity(alias, item, "Brand")
                    for prod in item.get("models_or_products", []):
                        self._register_entity(prod, item, "BrandProduct")
            except Exception as exc:
                logger.debug("Failed loading brands: %s", exc)

        # 4. Vehicles & Transport
        veh_path = self.data_dir / "vehicles_and_transport.json"
        if veh_path.is_file():
            try:
                self._vehicles = json.loads(veh_path.read_text(encoding="utf-8"))
                for item in self._vehicles:
                    self._register_entity(item.get("type_name", ""), item, "VehicleCategory")
                    self._register_entity(item.get("name_en", ""), item, "VehicleCategory")
                    for sub in item.get("subtypes", []):
                        self._register_entity(sub.get("name", ""), item, "VehicleSubtype")
                        self._register_entity(sub.get("name_en", ""), item, "VehicleSubtype")
                        for ex in sub.get("examples", []):
                            self._register_entity(ex, item, "VehicleModel")
            except Exception as exc:
                logger.debug("Failed loading vehicles: %s", exc)

        self._is_loaded = True
        logger.info(
            "Encyclopedic Knowledge Store initialized: %d indexed phrases across Landmarks, Traffic Signs, Brands & Vehicles.",
            len(self._entity_lookup),
        )

    def _register_entity(self, phrase: str, payload: dict[str, Any], entity_type: str) -> None:
        clean = phrase.strip().lower()
        if clean and len(clean) >= 2:
            self._entity_lookup[clean] = {"entity_type": entity_type, "data": payload}

    def match_entities_in_query(self, query: str) -> list[dict[str, Any]]:
        """Identify all domain entities (Traffic Signs, Brands, Vehicles, Landmarks) mentioned in query."""
        if not self._is_loaded:
            self.load_all()

        matched: list[dict[str, Any]] = []
        q_lower = query.lower()

        # Match longest phrases first to prevent partial overlaps
        # Compiled patterns are cached by the lru_cache on _get_phrase_pattern
        for phrase, entity_info in sorted(self._entity_lookup.items(), key=lambda x: len(x[0]), reverse=True):
            if self._get_phrase_pattern(phrase).search(q_lower):
                matched.append({
                    "matched_phrase": phrase,
                    "entity_type": entity_info["entity_type"],
                    "data": entity_info["data"],
                })

        return matched

    def ground_and_expand_query(self, query: str) -> tuple[str, list[str]]:
        """Extract matched visual keywords and return enriched query string with synonyms."""
        matches = self.match_entities_in_query(query)
        if not matches:
            return query, []

        tokens: list[str] = []
        additions: list[str] = []

        for m in matches:
            e_type = m["entity_type"]
            data = m["data"]

            if e_type == "TrafficSign":
                canon = data.get("name_en", "")
                if canon and canon.lower() not in query.lower():
                    additions.append(f"traffic sign: {canon}")
                tokens.extend(data.get("visual_cues", []))

            elif e_type in ("Brand", "BrandProduct"):
                brand_name = data.get("brand", "")
                tokens.extend(data.get("keywords", []))
                if brand_name and brand_name.lower() not in query.lower():
                    additions.append(brand_name)

            elif e_type == "Landmark":
                canon = data.get("canonical_en", "")
                if canon and canon.lower() not in query.lower():
                    additions.append(canon)
                tokens.extend(data.get("keywords", []))

            elif "Vehicle" in e_type:
                tokens.extend(data.get("keywords", []))

        enriched = query
        if additions:
            enriched = f"{query} ({', '.join(additions[:3])})"

        return enriched, list(set(tokens))


encyclopedic_store = EncyclopedicStore()
