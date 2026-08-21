"""Orthogonal Negative Constraint Subspace Projection (Gram-Schmidt) for AIC 2026.

Mathematically removes forbidden visual attributes from query vectors and penalizes
false-positive keyframes containing excluded concepts (e.g. 'không đội mũ bảo hiểm').
"""

from __future__ import annotations

import logging
import re
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# Multilingual negative constraint regex patterns
NEGATIVE_PATTERNS: list[tuple[str, str, str]] = [
    # (Regex pattern, positive entity fallback, negative entity fallback)
    # --- Vietnamese patterns ---
    (r"\bkhông (đội|mang|có) (mũ|nón) bảo hiểm\b", "person riding motorbike motorcycle", "helmet safety helmet on head"),
    (r"\bkhông (đội|mang) (mũ|nón)\b", "person", "hat cap helmet on head"),
    (r"\bkhông (mặc|có) áo\b", "shirtless person bare chest", "shirt jacket clothes upper body"),
    (r"\bkhông (đeo|mang) khẩu trang\b", "person face unmasked", "face mask medical mask"),
    (r"\bkhông có (người|nguoi)\b", "empty scene street background", "person people human"),
    (r"\bkhông có (xe|ô tô|xe hơi)\b", "empty road pedestrian zone", "car automobile vehicle"),
    (r"\bkhông phải màu (\w+)\b", "object", "color \\1"),
    # --- English patterns (exact + Google Translate variants) ---
    (r"\bwithout (a |an )?helmet\b", "motorcyclist riding motorbike", "helmet safety helmet on head"),
    (r"\bnot wearing (a |an )?helmet\b", "motorcyclist riding motorbike", "helmet safety helmet on head"),
    (r"\bno helmet\b", "motorcyclist riding motorbike", "helmet safety helmet on head"),
    (r"\bwithout (wearing )?(a |an )?shirt\b", "shirtless person bare chest", "shirt jacket clothes upper body"),
    (r"\bnot wearing (a |an )?shirt\b", "shirtless person bare chest", "shirt jacket clothes upper body"),
    (r"\bshirtless\b", "shirtless person bare chest", "shirt jacket clothes upper body"),
    (r"\bwithout (a |an )?mask\b", "unmasked face", "face mask surgical mask"),
    (r"\bnot wearing (a |an )?mask\b", "unmasked face", "face mask surgical mask"),
    (r"\bno mask\b", "unmasked face", "face mask surgical mask"),
    (r"\bno (people|person|one)\b", "empty background landscape", "person people human"),
    (r"\bwithout (a |an )?seatbelt\b", "driver in car", "seatbelt safety belt"),
    (r"\bnot wearing (a |an )?seatbelt\b", "driver in car", "seatbelt safety belt"),
]


def extract_negative_constraint(query: str) -> tuple[bool, str, str]:
    """
    Extract (has_negative, positive_text, negative_text) from a natural language query.
    """
    cleaned = query.strip()
    lower_q = cleaned.lower()

    for pat, pos_def, neg_def in NEGATIVE_PATTERNS:
        match = re.search(pat, lower_q)
        if match:
            # Slices positive part
            pos_part = re.sub(pat, "", cleaned, flags=re.IGNORECASE).strip()
            if not pos_part or len(pos_part.split()) < 2:
                pos_part = pos_def
            neg_part = match.group(0)
            if "\\1" in neg_def and match.groups():
                neg_part = neg_def.replace("\\1", match.group(1))
            else:
                neg_part = neg_def
            return True, pos_part, neg_part

    # Generic "without X" / "không có X"
    gen_match = re.search(r"\b(without|không có|không phải)\s+([^,]+)", lower_q)
    if gen_match:
        neg_part = gen_match.group(2).strip()
        pos_part = re.sub(r"\b(without|không có|không phải)\s+[^,]+", "", cleaned, flags=re.IGNORECASE).strip()
        if pos_part:
            return True, pos_part, neg_part

    return False, cleaned, ""


def project_orthogonal_negative_vector(
    pos_vector: np.ndarray,
    neg_vector: np.ndarray,
    alpha: float = 0.85,
) -> np.ndarray:
    """
    Gram-Schmidt projection of positive vector onto the orthogonal complement of the negative subspace:
    v* = v_pos - alpha * (v_pos . v_neg) * v_neg
    """
    v_p = pos_vector.flatten().astype(np.float32)
    v_n = neg_vector.flatten().astype(np.float32)

    norm_p = np.linalg.norm(v_p)
    norm_n = np.linalg.norm(v_n)

    if norm_p > 0:
        v_p = v_p / norm_p
    if norm_n > 0:
        v_n = v_n / norm_n

    dot_product = float(np.dot(v_p, v_n))

    # If already orthogonal or negatively correlated, no projection needed
    if dot_product <= 0.0:
        return v_p

    # Gram-Schmidt subtraction
    v_proj = v_p - (alpha * dot_product * v_n)
    norm_proj = float(np.linalg.norm(v_proj))

    if norm_proj > 0:
        return (v_proj / norm_proj).astype(np.float32)
    return v_p


def apply_negative_constraint_to_query(
    query: str,
    text_encoder: Any,
    alpha: float = 0.85,
) -> tuple[np.ndarray, bool, str, str]:
    """
    Checks for negative constraints, encodes positive and negative concepts,
    and returns (projected_vector, has_neg, pos_text, neg_text).
    """
    has_neg, pos_text, neg_text = extract_negative_constraint(query)
    if not has_neg:
        vec = text_encoder.encode(query).flatten().astype(np.float32)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec, False, query, ""

    try:
        if hasattr(text_encoder, "encode_batch"):
            batch = text_encoder.encode_batch([pos_text, neg_text])
            v_pos = batch[0]
            v_neg = batch[1]
        else:
            v_pos = text_encoder.encode(pos_text)
            v_neg = text_encoder.encode(neg_text)

        v_final = project_orthogonal_negative_vector(v_pos, v_neg, alpha=alpha)
        return v_final, True, pos_text, neg_text
    except Exception as exc:
        logger.warning("Negative projection failed: %s; fallback to standard encode", exc)
        vec = text_encoder.encode(pos_text).flatten().astype(np.float32)
        return vec, True, pos_text, neg_text
