"""Perceptual Visual Hash (dHash) & Cache for instant VQA duplicate skipping."""

from __future__ import annotations

import logging

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

# Key: normalized question -> list of (dhash: int, answer: str)
_VISUAL_ANSWER_CACHE: dict[str, list[tuple[int, str]]] = {}
_MAX_CACHE_ENTRIES_PER_QUESTION = 64


def compute_dhash(img: Image.Image, hash_size: int = 8) -> int:
    """Compute 64-bit difference hash (dHash) for an image in < 0.5ms."""
    try:
        resized = img.convert("L").resize((hash_size + 1, hash_size), Image.Resampling.BILINEAR)
        arr = np.asarray(resized, dtype=np.int16)
        diff = arr[:, 1:] > arr[:, :-1]
        flat = diff.flatten()
        val = 0
        for b in flat:
            val = (val << 1) | int(b)
        return val
    except Exception as exc:
        logger.debug("Failed computing dHash: %s", exc)
        return 0


def hamming_distance(h1: int, h2: int) -> int:
    """Calculate the Hamming bit difference between two 64-bit perceptual hashes."""
    return bin(h1 ^ h2).count("1")


def lookup_visual_cache(
    question: str,
    img: Image.Image,
    hamming_threshold: int = 3,
) -> str | None:
    """Look up cached answer if an identical or near-identical image was already evaluated for this question."""
    q_norm = question.strip().lower()
    if q_norm not in _VISUAL_ANSWER_CACHE:
        return None

    img_hash = compute_dhash(img)
    if img_hash == 0:
        return None

    for cached_hash, cached_ans in _VISUAL_ANSWER_CACHE[q_norm]:
        if hamming_distance(img_hash, cached_hash) <= hamming_threshold:
            logger.info("Visual hash cache HIT for question '%s' (dist <= %d)", q_norm[:30], hamming_threshold)
            return cached_ans

    return None


def store_visual_cache(question: str, img: Image.Image, answer: str) -> None:
    """Store evaluated answer indexed by question and perceptual visual hash."""
    if not answer.strip():
        return

    q_norm = question.strip().lower()
    img_hash = compute_dhash(img)
    if img_hash == 0:
        return

    if q_norm not in _VISUAL_ANSWER_CACHE:
        _VISUAL_ANSWER_CACHE[q_norm] = []

    entries = _VISUAL_ANSWER_CACHE[q_norm]
    # Check if hash already exists
    for idx, (h, _) in enumerate(entries):
        if hamming_distance(img_hash, h) <= 1:
            entries[idx] = (img_hash, answer)
            return

    if len(entries) >= _MAX_CACHE_ENTRIES_PER_QUESTION:
        entries.pop(0)

    entries.append((img_hash, answer))
