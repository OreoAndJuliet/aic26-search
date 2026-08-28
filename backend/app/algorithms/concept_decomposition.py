"""Multi-Concept Semantic Decomposition & Dynamic Saliency Weighting for complex KIS queries."""

from __future__ import annotations

import logging
import re
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# Prepositional and relational scene patterns
SCENE_PREPOSITIONS = (
    "in front of", "behind", "next to", "near", "on top of", "inside", "outside",
    "at the", "in a", "in the", "on a", "on the", "across", "along", "by the", "under"
)

# Active verbs and actions
ACTION_PATTERNS = [
    r"\b(?:walking|running|standing|sitting|riding|driving|swimming|flying|eating|cooking|talking|holding|carrying|dancing|jumping|playing|crossing|entering|leaving)\b",
    r"\b(?:đang đi|đang chạy|đang đứng|đang ngồi|đang lái|đang bơi|đang ăn|đang nói|đang cầm|đang chơi|đi qua|bước vào)\b",
]

# Visual attributes and colors
ATTRIBUTE_PATTERNS = [
    r"\b(?:wearing|dressed in|in red|in blue|in white|in black|in yellow|in green|in pink|in purple|in orange|in grey|in gray)\b",
    r"\b(?:red|blue|green|yellow|white|black|silver|pink|purple|orange|gray|grey|golden|wooden|metallic|glass|plastic|leather|small|large|tall|short|old|young)\b",
    r"\b(?:mặc|đeo|màu đỏ|màu xanh|màu vàng|màu trắng|màu đen|màu hồng|màu tím|màu cam|màu xám|bằng gỗ|bằng kính|nhỏ|to|lớn|cao|thấp)\b",
]

# Primary entity nouns
ENTITY_PATTERNS = [
    r"\b(?:person|people|man|men|woman|women|child|children|boy|girl|police|officer|driver|rider|pedestrian|dog|cat|bird|horse|cow|car|bus|truck|bicycle|bike|motorbike|motorcycle|boat|ship|airplane|plane|train|lion|dragon|costume|dance|helicopter|scooter)\b",
    r"\b(?:người|đàn ông|phụ nữ|trẻ em|bé trai|bé gái|công an|cảnh sát|tài xế|chó|mèo|chim|ngựa|bò|xe hơi|xe buýt|xe tải|xe đạp|xe máy|thuyền|tàu|máy bay|tàu hỏa|sư tử|rồng|trang phục|múa|trực thăng)\b",
]

# High-information vs low-information vocabulary for linguistic entropy
GENERIC_FILLERS = {
    "person", "man", "woman", "someone", "people", "thing", "object", "room",
    "scene", "background", "street", "place", "area", "photo", "image", "frame",
    "outside", "indoor", "outdoor", "video", "view",
}

HIGH_INFO_COLORS = {
    "red", "yellow", "blue", "green", "pink", "purple", "orange", "black",
    "white", "golden", "silver", "neon", "bright", "dark", "cyan", "magenta",
}

HIGH_INFO_OBJECTS = {
    "helmet", "umbrella", "raincoat", "jacket", "coat", "guitar", "laptop",
    "knife", "avocado", "bottle", "cup", "teapot", "bridge", "car", "bicycle",
    "motorcycle", "apron", "sink", "plate", "bowl", "dress", "hat", "backpack",
}


def compute_concept_saliency_score(text: str, concept_type: str) -> float:
    """Calculate linguistic information entropy and discriminative specificity score for a sub-concept."""
    if not text.strip():
        return 0.0

    words = re.findall(r"\b\w+\b", text.lower())
    if not words:
        return 0.0

    base_weight = {
        "landmark": 0.50,
        "global": 0.35,
        "attribute": 0.25,
        "entity": 0.20,
        "action": 0.15,
        "scene": 0.10,
    }.get(concept_type, 0.20)

    multiplier = 1.0

    # 1. Landmark & Unique architecture massive boost
    if concept_type == "landmark" or any(w in ("market", "palace", "cathedral", "pagoda", "tower", "bridge", "wharf", "mausoleum", "citadel", "opera") for w in words):
        multiplier += 2.0

    # 2. Distinctive culture/slang/action entity boost
    distinctive_terms = {
        "ninja", "shipper", "csgt", "helmet", "watch", "crosswalk", "zebra", "coffee",
        "sidewalk", "stool", "table", "bus", "truck", "umbrella", "raincoat", "glasses",
        "sunglasses", "handbag", "backpack", "bottle", "plate", "guitar", "laptop",
        "bến thành", "landmark 81", "cầu rồng", "áo chống nắng", "vỉa hè", "cà phê",
    }
    dist_matches = sum(1 for w in words if w in distinctive_terms)
    if dist_matches > 0:
        multiplier += 0.85 * dist_matches

    # 3. Color specificity boost
    color_matches = sum(1 for w in words if w in HIGH_INFO_COLORS)
    if color_matches > 0:
        multiplier += 0.60 * color_matches

    # 4. Rare/specific object boost
    obj_matches = sum(1 for w in words if w in HIGH_INFO_OBJECTS)
    if obj_matches > 0:
        multiplier += 0.50 * obj_matches

    # 5. Generic high-frequency filler down-weighting (Entropy attenuation)
    generic_matches = sum(1 for w in words if w in GENERIC_FILLERS)
    if generic_matches > 0 and len(words) <= 2:
        multiplier *= 0.40

    # 6. Multi-word modifier depth boost
    if len(words) >= 2:
        multiplier += 0.15 * min(3, len(words) - 1)

    return base_weight * multiplier


def calculate_dynamic_saliency_weights(concepts: dict[str, str]) -> dict[str, float]:
    """Dynamically assign proportional weights based on linguistic information entropy."""
    scores: dict[str, float] = {}
    for c_type, text in concepts.items():
        if text:
            scores[c_type] = compute_concept_saliency_score(text, c_type)
        else:
            scores[c_type] = 0.0

    total = sum(scores.values())
    if total > 0:
        return {k: v / total for k, v in scores.items()}
    return {k: 0.2 for k in concepts}


def decompose_query_concepts(query: str) -> dict[str, str]:
    """Decompose a natural language query into semantic components: entity, attribute, action, scene."""
    cleaned = query.strip()
    if not cleaned:
        return {}

    lower_q = cleaned.lower()
    concepts: dict[str, str] = {"global": cleaned}

    # 1. Extract Landmark / Domain Entity (Check encyclopedic knowledge store first)
    try:
        from app.services.encyclopedic_store import encyclopedic_store
        matched_entities = encyclopedic_store.match_entities_in_query(cleaned)
        if matched_entities:
            top_entity = matched_entities[0]
            e_data = top_entity.get("data", {})
            canon = e_data.get("canonical_en", top_entity["matched_phrase"])
            cues = " ".join(e_data.get("keywords", [])[:4])
            concepts["landmark"] = f"a photo of {canon} landmark building {cues}".strip()
            concepts["entity"] = f"a photo of {canon}"
    except Exception as exc:
        logger.debug("Encyclopedic entity lookup error: %s", exc)

    if "entity" not in concepts:
        entities = []
        for pat in ENTITY_PATTERNS:
            matches = re.findall(pat, lower_q)
            if matches:
                entities.extend(matches)
        if entities:
            unique_ents = list(dict.fromkeys(entities))
            concepts["entity"] = f"a photo of {' and '.join(unique_ents)}"

    # 2. Extract Attribute / Color
    attributes = []
    for pat in ATTRIBUTE_PATTERNS:
        matches = re.findall(pat, lower_q)
        if matches:
            attributes.extend(matches)
    if attributes:
        unique_attrs = list(dict.fromkeys(attributes))
        concepts["attribute"] = " ".join(unique_attrs)

    # 3. Extract Action / Verb
    for pat in ACTION_PATTERNS:
        match = re.search(pat, lower_q)
        if match:
            action_word = match.group(0)
            concepts["action"] = action_word
            break

    # 4. Extract Scene / Setting
    for prep in SCENE_PREPOSITIONS:
        idx = lower_q.find(prep)
        if idx != -1:
            scene_text = cleaned[idx:].strip()
            if len(scene_text.split()) >= 2:
                concepts["scene"] = scene_text
                break

    return concepts


def build_multiconcept_fused_vector(
    query: str,
    text_encoder: Any,
    *,
    w_global: float = 0.45,
    w_entity: float = 0.20,
    w_attribute: float = 0.15,
    w_action: float = 0.10,
    w_scene: float = 0.10,
    use_dynamic_saliency: bool = True,
) -> np.ndarray:
    """Encode query sub-concepts in a single batch forward pass and return an L2-normalized composite vector."""
    concepts = decompose_query_concepts(query)
    if not concepts:
        return text_encoder.encode(query).flatten().astype(np.float32)

    # Prepare batch of all non-empty sub-concepts
    concept_keys = [k for k, v in concepts.items() if v]
    concept_texts = [concepts[k] for k in concept_keys]

    if not concept_texts:
        return text_encoder.encode(query).flatten().astype(np.float32)

    # Encode all sub-concepts in 1 single forward pass
    try:
        if hasattr(text_encoder, "encode_batch"):
            batch_vectors = text_encoder.encode_batch(concept_texts)
        else:
            batch_vectors = np.vstack([text_encoder.encode(t) for t in concept_texts])
    except Exception as exc:
        logger.debug("Batch encoding fallback to single encode: %s", exc)
        batch_vectors = np.vstack([text_encoder.encode(t) for t in concept_texts])

    # Calculate dynamic saliency weights
    if use_dynamic_saliency:
        weights_map = calculate_dynamic_saliency_weights(concepts)
    else:
        weights_map = {
            "global": w_global,
            "landmark": 0.40,
            "entity": w_entity,
            "attribute": w_attribute,
            "action": w_action,
            "scene": w_scene,
        }

    composite_vec = np.zeros(batch_vectors.shape[1], dtype=np.float32)
    total_weight = 0.0

    for i, key in enumerate(concept_keys):
        v = batch_vectors[i].flatten().astype(np.float32)
        norm_v = np.linalg.norm(v)
        if norm_v > 0:
            v = v / norm_v
            w = weights_map.get(key, 0.20)
            composite_vec += w * v
            total_weight += w

    if total_weight > 0:
        composite_vec = composite_vec / total_weight

    norm = float(np.linalg.norm(composite_vec))
    if norm > 0:
        return (composite_vec / norm).astype(np.float32).reshape(-1)
    return batch_vectors[0].flatten().astype(np.float32).reshape(-1)
