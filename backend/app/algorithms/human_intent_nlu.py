"""Colloquial Vietnamese Natural Language Understanding & Cultural Intent Engine for AIC 2026.

Parses culture-specific Vietnamese attire, conversational slang, compound actions,
and separates positive vs negative constraints for downstream retrieval.
"""

from __future__ import annotations

import logging
import re
import json
from pathlib import Path
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Culture-specific attire, occupations, and colloquial entity mappings
VIETNAMESE_CULTURAL_ENTITIES: dict[str, dict[str, str | list[str]]] = {}

# Compound actions and simultaneous gestures
COMPOUND_ACTION_PATTERNS: list[tuple[str, str]] = []

def _load_datasets():
    global VIETNAMESE_CULTURAL_ENTITIES, COMPOUND_ACTION_PATTERNS
    data_dir = Path(__file__).resolve().parent.parent.parent / "data"
    
    cultural_path = data_dir / "cultural_entities.json"
    if cultural_path.exists():
        try:
            with open(cultural_path, "r", encoding="utf-8") as f:
                VIETNAMESE_CULTURAL_ENTITIES = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load cultural_entities.json: {e}")
            
    actions_path = data_dir / "action_mappings.json"
    if actions_path.exists():
        try:
            with open(actions_path, "r", encoding="utf-8") as f:
                raw_actions = json.load(f)
                COMPOUND_ACTION_PATTERNS = [(item["pattern"], item["canonical_en"]) for item in raw_actions]
        except Exception as e:
            logger.error(f"Failed to load action_mappings.json: {e}")

_load_datasets()

# Negative constraint markers
NEGATIVE_MARKERS_VI: list[str] = [
    "không đội mũ bảo hiểm",
    "không đội mũ",
    "không có nón bảo hiểm",
    "không mặc áo",
    "không mang khẩu trang",
    "không có người",
    "không có xe",
    "không phải",
    "không có",
    "chưa có",
    "chẳng có",
]


@dataclass
class ParsedHumanIntent:
    original_query: str
    cleaned_query: str
    cultural_entities: list[dict[str, str]] = field(default_factory=list)
    compound_actions: list[str] = field(default_factory=list)
    has_negative_constraint: bool = False
    positive_concept: str = ""
    negative_concept: str = ""
    enriched_english_prompt: str = ""


def parse_human_intent(query: str) -> ParsedHumanIntent:
    """Parse colloquial Vietnamese phrasing, cultural slang, compound actions, and negative constraints."""
    cleaned = query.strip()
    lower_q = cleaned.lower()

    result = ParsedHumanIntent(
        original_query=cleaned,
        cleaned_query=cleaned,
        positive_concept=cleaned,
    )

    if not cleaned:
        return result

    # 1. Match cultural entities
    matched_cues: list[str] = []
    for ent_id, ent_info in VIETNAMESE_CULTURAL_ENTITIES.items():
        patterns = ent_info.get("patterns", [])
        for pat in patterns:
            if re.search(pat, lower_q):
                canon = str(ent_info.get("canonical_en", ""))
                kws = " ".join(ent_info.get("keywords", [])[:3])
                result.cultural_entities.append({
                    "id": ent_id,
                    "canonical_en": canon,
                    "keywords": kws,
                })
                matched_cues.append(canon)
                break

    # 2. Match compound actions
    for act_pat, act_en in COMPOUND_ACTION_PATTERNS:
        if re.search(act_pat, lower_q):
            result.compound_actions.append(act_en)
            matched_cues.append(act_en)

    # 3. Detect and separate negative constraints
    for marker in NEGATIVE_MARKERS_VI:
        m = re.search(rf"\b{re.escape(marker)}\b", lower_q)
        if m:
            # Prevent false positives on non-negative compound words
            if any(compound in lower_q for compound in ("không gian", "không khí", "hàng không", "hư không")):
                if marker not in ("không đội mũ bảo hiểm", "không đội mũ", "không có nón bảo hiểm", "không mặc áo", "không mang khẩu trang", "không có người", "không có xe"):
                    continue

            idx = m.start()
            result.has_negative_constraint = True
            pos_part = cleaned[:idx].strip()
            neg_part = cleaned[m.end():].strip()
            
            # Formulate explicit positive and negative entities
            if "mũ" in marker or "nón" in marker:
                result.positive_concept = pos_part or cleaned
                result.negative_concept = "helmet safety helmet on head"
            elif "áo" in marker:
                result.positive_concept = pos_part or cleaned
                result.negative_concept = "shirt jacket upper body clothing"
            elif "khẩu trang" in marker:
                result.positive_concept = pos_part or cleaned
                result.negative_concept = "face mask medical mask"
            else:
                result.positive_concept = pos_part or cleaned
                result.negative_concept = neg_part or marker
            break

    # 4. Formulate enriched prompt
    if matched_cues:
        result.enriched_english_prompt = ", ".join(dict.fromkeys(matched_cues))

    return result
