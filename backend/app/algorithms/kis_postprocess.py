"""Post-retrieval KIS reranking using Objects JSON and media-info keywords."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.config import settings
from app.services.media_info_store import media_info_store
from app.services.object_store import object_store

OBJECT_ALIASES: dict[str, tuple[str, ...]] = {
    "person": ("person", "people", "human", "man", "woman", "child", "children", "nguoi", "người", "đàn ông", "phụ nữ", "trẻ em"),
    "car": ("car", "cars", "automobile", "vehicle", "land vehicle", "xe", "xe hoi", "xe hơi", "xe ô tô", "xe oto"),
    "bus": ("bus", "buses", "xe buýt", "xe buyt"),
    "truck": ("truck", "trucks", "xe tải", "xe tai"),
    "motorbike": ("motorbike", "motorcycle", "motorbikes", "motorcycles", "xe may", "xe máy"),
    "bicycle": ("bicycle", "bike", "bicycles", "bikes", "xe dap", "xe đạp"),
    "dog": ("dog", "dogs", "puppy", "cho", "chó", "cún"),
    "cat": ("cat", "cats", "kitten", "meo", "mèo"),
    "cup": ("cup", "mug", "glass", "coc", "cốc", "ly"),
    "bottle": ("bottle", "bottles", "chai"),
    "chair": ("chair", "chairs", "ghe", "ghế"),
    "table": ("table", "tables", "desk", "desks", "ban", "bàn"),
    "phone": ("phone", "mobile", "cellphone", "dien thoai", "điện thoại"),
    "building": ("building", "buildings", "skyscraper", "tower", "house", "tòa nhà", "toa nha", "nhà"),
    "tree": ("tree", "trees", "plant", "plants", "cây", "cay"),
}


@dataclass(frozen=True)
class ObjectConstraint:
    target_class: str
    min_count: int = 1


_COUNT_PATTERN_EN = re.compile(
    r"\b(\d+)\s+(cars?|people|persons?|men|women|children|dogs?|cats?|cups?|bottles?|"
    r"chairs?|tables?|phones?|bicycles?|bikes?|buses?|trucks?|motorbikes?|trees?|buildings?)\b",
    re.IGNORECASE,
)

_VN_NUMBER_MAP = {
    "một": 1, "mot": 1, "1": 1,
    "hai": 2, "2": 2,
    "ba": 3, "3": 3,
    "bốn": 4, "bon": 4, "4": 4,
    "năm": 5, "nam": 5, "5": 5,
}

_COUNT_PATTERN_VN = re.compile(
    r"\b(\d+|một|mot|hai|ba|bốn|bon|năm|nam)\s+(người|nguoi|chiếc xe|chiec xe|xe hơi|xe hoi|xe máy|xe may|xe đạp|xe dap|xe ô tô|xe oto|con chó|con cho|con mèo|con meo|cái bàn|cai ban|cái ghế|cai ghe|chai|cốc|coc|ly)\b",
    re.IGNORECASE,
)


def parse_object_constraints(query: str) -> list[ObjectConstraint]:
    normalized = query.casefold()
    constraints: list[ObjectConstraint] = []

    for match in _COUNT_PATTERN_EN.finditer(normalized):
        count = int(match.group(1))
        label = match.group(2)
        target = _normalize_object_label(label)
        if target:
            constraints.append(ObjectConstraint(target_class=target, min_count=count))

    for match in _COUNT_PATTERN_VN.finditer(normalized):
        num_str = match.group(1).lower()
        count = _VN_NUMBER_MAP.get(num_str, 1)
        label = match.group(2)
        target = _normalize_object_label(label)
        if target and not any(c.target_class == target for c in constraints):
            constraints.append(ObjectConstraint(target_class=target, min_count=count))

    if constraints:
        return constraints

    for target_class, aliases in OBJECT_ALIASES.items():
        if any(re.search(rf"\b{re.escape(alias)}\b", normalized) for alias in aliases):
            constraints.append(ObjectConstraint(target_class=target_class, min_count=1))

    return constraints


def _normalize_object_label(label: str) -> str | None:
    token = label.casefold().strip()
    for target_class, aliases in OBJECT_ALIASES.items():
        if any(token == alias or token.rstrip("s") == alias for alias in aliases):
            return target_class
    return None


def _object_boost(result: dict, constraints: list[ObjectConstraint]) -> float:
    if not constraints:
        return 0.0

    video_id = str(result.get("video_id", ""))
    keyframe_id = int(result.get("keyframe_id", result.get("frame_id", 0)))
    total_boost = 0.0
    weight = settings.KIS_OBJECT_RERANK_WEIGHT

    for constraint in constraints:
        detections = object_store.count_by_class(
            video_id,
            keyframe_id,
            constraint.target_class,
            threshold=0.45,
        )
        count = len(detections)
        avg_score = sum(d["score"] for d in detections) / count if count > 0 else 0.0

        if count >= constraint.min_count:
            # Positive boost scaled by detection confidence
            boost = 0.06 * min(count, 3) + 0.04 * avg_score
            if count == constraint.min_count:
                boost += 0.03  # Exact count bonus
            total_boost += boost * (weight / 0.10)
        else:
            # Soft penalty for missing required entities
            total_boost -= 0.05 * (weight / 0.10)

    return total_boost


def rerank_kis_by_objects(query: str, results: list[dict]) -> list[dict]:
    if not settings.KIS_OBJECT_RERANK_ENABLED or not results:
        return results

    constraints = parse_object_constraints(query)
    if not constraints:
        return results

    reranked: list[dict] = []
    for item in results:
        copy = dict(item)
        object_boost = _object_boost(copy, constraints)
        copy["object_boost"] = round(object_boost, 6)
        new_score = round(float(copy.get("score", 0.0)) + object_boost, 6)
        copy["score"] = new_score
        # Keep r_score in sync so sort order is consistent with score
        copy["r_score"] = new_score
        reranked.append(copy)

    reranked.sort(key=lambda row: (
        -float(row.get("score", 0.0)),
        int(row.get("rank", 999))
    ))
    for rank, item in enumerate(reranked, start=1):
        item["rank"] = rank
    return reranked


def rerank_kis_by_media_info(query: str, results: list[dict]) -> list[dict]:
    if not settings.KIS_MEDIA_INFO_RERANK_ENABLED or not results:
        return results

    reranked: list[dict] = []
    for item in results:
        copy = dict(item)
        media_boost = round(
            media_info_store.keyword_score(str(copy["video_id"]), query)
            * settings.KIS_MEDIA_INFO_RERANK_WEIGHT,
            6,
        )
        copy["media_boost"] = media_boost
        new_score = round(float(copy.get("score", 0.0)) + media_boost, 6)
        copy["score"] = new_score
        # Keep r_score in sync so sort order is consistent with score
        copy["r_score"] = new_score
        reranked.append(copy)

    reranked.sort(key=lambda row: (
        -float(row.get("score", 0.0)),
        int(row.get("rank", 999))
    ))
    for rank, item in enumerate(reranked, start=1):
        item["rank"] = rank
    return reranked
