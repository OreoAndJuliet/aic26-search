"""Colloquial Vietnamese Natural Language Understanding & Cultural Intent Engine for AIC 2026.

Parses culture-specific Vietnamese attire, conversational slang, compound actions,
and separates positive vs negative constraints for downstream retrieval.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Culture-specific attire, occupations, and colloquial entity mappings
VIETNAMESE_CULTURAL_ENTITIES: dict[str, dict[str, str | list[str]]] = {
    "ninja": {
        "patterns": [r"\bninja\b", r"\báo chống nắng ninja\b", r"\bnữ ninja\b", r"\bnin ja\b"],
        "canonical_en": "person wearing full sun UV protection hoodie jacket mask face cover sunglasses riding motorbike",
        "keywords": ["sun protective clothing", "hoodie jacket", "face mask", "gloves", "female motorbike rider"],
    },
    "shipper": {
        "patterns": [r"\bshipper\b", r"\banh shipper\b", r"\bngười giao hàng\b", r"\bgiao hàng\b", r"\bshiper\b"],
        "canonical_en": "delivery driver courier with large thermal backpack delivery box on motorbike",
        "keywords": ["delivery box", "courier backpack", "insulated bag", "cargo rack", "delivery parcel"],
    },
    "csgt": {
        "patterns": [r"\bcsgt\b", r"\bcảnh sát giao thông\b", r"\bchú csgt\b", r"\bcông an giao thông\b", r"\bcông an áo vàng\b"],
        "canonical_en": "traffic police officer in beige yellow uniform with traffic wand cap",
        "keywords": ["yellow uniform", "police badge", "traffic wand", "officer cap", "traffic control"],
    },
    "xe_om_cong_nghe": {
        "patterns": [r"\bxe ôm công nghệ\b", r"\btài xế công nghệ\b", r"\bxe ôm grab\b", r"\btài xế grab\b", r"\btài xế be\b"],
        "canonical_en": "ride-hailing motorbike driver wearing green or yellow uniform jacket helmet Grab Be Gojek",
        "keywords": ["ride hailing jacket", "green helmet", "yellow jacket", "smartphone phone mount"],
    },
    "xe_keo_hang": {
        "patterns": [r"\bxe kéo hàng\b", r"\bxe ba gác\b", r"\bxe đẩy hàng\b", r"\bxe xích lô\b"],
        "canonical_en": "three-wheeled cargo cart tricycle handcart loaded with goods boxes",
        "keywords": ["cargo cart", "loaded merchandise", "flatbed cart", "handcart"],
    },
    "xe_ve_chai": {
        "patterns": [r"\bxe ve chai\b", r"\bngười mua ve chai\b", r"\blượm ve chai\b", r"\bthu gom phế liệu\b"],
        "canonical_en": "person pushing cart collecting recyclable scrap cardboard bottles",
        "keywords": ["scrap collector", "recycling cart", "cardboard scrap", "conical hat"],
    },
    "ganh_hang_rong": {
        "patterns": [r"\bgánh hàng rong\b", r"\bbán hàng rong\b", r"\bngười gánh hàng\b", r"\bđòn gánh\b"],
        "canonical_en": "street vendor carrying shoulder pole with two baskets conical hat",
        "keywords": ["shoulder pole", "woven baskets", "street vendor", "conical non la"],
    },
    "xe_nuoc_mia": {
        "patterns": [r"\bxe nước mía\b", r"\bquán nước mía\b", r"\bmáy ép mía\b"],
        "canonical_en": "sugarcane juice press cart stall with stalks of sugarcane",
        "keywords": ["sugarcane press", "juice stall", "beverage cart", "street stall"],
    },
    "xe_banh_mi": {
        "patterns": [r"\bxe bánh mì\b", r"\btủ bánh mì\b", r"\bquán bánh mì\b"],
        "canonical_en": "vietnamese banh mi sandwich glass cart display stall on sidewalk",
        "keywords": ["glass display cart", "baguettes", "street food stall"],
    },
}

# Compound actions and simultaneous gestures
COMPOUND_ACTION_PATTERNS: list[tuple[str, str]] = [
    (r"\bvừa đi vừa (bấm|xem|dùng|lướt) điện thoại\b", "person riding motorbike while looking at smartphone handheld phone"),
    (r"\bvừa lái xe vừa (nghe|gọi) điện thoại\b", "driver holding smartphone to ear while driving vehicle"),
    (r"\bngười đi bộ.*(băng|qua|sang|bước).*đường.*(vạch|kẻ|vạch kẻ|trắng)?\b", "pedestrian walking across crosswalk zebra crossing line street"),
    (r"\bngười đi bộ bước trên vạch kẻ đường\b", "pedestrian walking across crosswalk zebra crossing line street"),
    (r"\b(vượt|chạy) đèn đỏ\b", "vehicle running red traffic light intersection"),
    (r"\bchở (hàng|đồ) cồng kềnh\b", "motorbike overloaded with bulky oversized cargo packages boxes"),
    (r"\bchở (ba|bốn|nhiều) người\b", "motorbike carrying multiple three four passengers without helmets"),
    (r"\bngười? ngồi uống cà phê( vỉa hè| bàn ghế)?\b", "people sitting on low plastic stools drinking coffee on street sidewalk cafe"),
    (r"\bdắt chó đi dạo\b", "person walking leashed dog in park or on sidewalk"),
    (r"\bmặc áo mưa (chạy|đi) xe\b", "motorcyclist wearing poncho raincoat riding in rain"),
    (r"\b(đeo|mang) đồng hồ\b", "person wearing wristwatch wrist watch on hand"),
    (r"\bxe buýt màu xanh( lá| lá cây)?\b", "green city bus public transit vehicle on road"),
    (r"\bbàn (bằng )?gỗ\b", "wooden dining table wooden furniture in kitchen or room"),
]

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
