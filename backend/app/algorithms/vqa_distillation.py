"""VQA Interrogative Focus Distillation & Conversational Fluff Cleaner."""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

CONVERSATIONAL_PREFIXES: list[str] = [
    r"^(?:can you please|could you please|please|can you|could you|would you|tell me|let me know|i want to know)\s+(?:look at\s+(?:the\s+)?(?:image|picture|video|frame|scene)\s+(?:and\s+)?)?",
    r"^(?:cho tôi biết|hãy cho biết|làm ơn cho biết|bạn có thể cho biết|hãy nói cho tôi|cho em biết)\s+",
    r"^(?:in this video frame|in this image|in the picture|in this photo|nhìn vào ảnh|trong hình)\s*,?\s*",
    r"^(?:what do you think is|in your opinion what is)\s+",
    r"^(?:look at the (?:table|image|frame|scene|picture) and (?:tell me|describe)?)\s+",
]

INTERROGATIVE_TARGET_PATTERNS: list[tuple[str, str]] = [
    (r"\b(?:what fruit|which fruit)\b", "fruit"),
    (r"\b(?:what color|which color|màu gì)\b", "color"),
    (r"\b(?:how many|có bao nhiêu|bao nhiêu)\b", "count"),
    (r"\b(?:what object|what item|cái gì|vật gì)\b", "object"),
    (r"\b(?:what beverage|what drink|đồ uống gì)\b", "drink"),
    (r"\b(?:who is|ai đang|người nào)\b", "person"),
    (r"\b(?:what is .+ holding|đang cầm gì)\b", "held_item"),
    (r"\b(?:what is .+ doing|đang làm gì)\b", "action"),
]


def clean_conversational_fluff(question: str) -> str:
    """Strip conversational opening filler to expose the core interrogative question."""
    q = question.strip()
    for _ in range(2):  # Two passes to catch nested openers like 'Can you please look at image and tell me...'
        for pat in CONVERSATIONAL_PREFIXES:
            q = re.sub(pat, "", q, flags=re.IGNORECASE).strip()

    if q and len(q) > 1:
        q = q[0].upper() + q[1:]
    return q if q else question


def extract_interrogative_target(question: str) -> str | None:
    """Identify the specific target attribute being queried."""
    q_lower = question.lower()
    for pat, target_name in INTERROGATIVE_TARGET_PATTERNS:
        if re.search(pat, q_lower):
            return target_name
    return None


def build_saliency_focused_prompt(question: str) -> str:
    """Distill natural language question into a concise, high-saliency prompt for VLMs."""
    clean_q = clean_conversational_fluff(question)
    target = extract_interrogative_target(clean_q)

    if not target or target == "count":
        # Keep standard format for counting or general questions
        return (
            f"Question: {clean_q}\n"
            f"Instruction: Answer concisely in 1 to 3 words. Do not explain."
        )

    return (
        f"Question: {clean_q}\n"
        f"Target Focus: {target.upper()}\n"
        f"Instruction: Answer concisely with only the exact {target} name or attribute in 1 to 3 words. "
        f"Do not repeat background container words."
    )
