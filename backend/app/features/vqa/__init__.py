"""VQA use-case layer (object-count heuristics + VLM fallback)."""

from app.features.vqa.service import (
    answer_vqa_question,
    is_person_count_question,
    parse_counting_target,
    parse_existence_target,
)

__all__ = [
    "answer_vqa_question",
    "is_person_count_question",
    "parse_counting_target",
    "parse_existence_target",
]
