"""Multi-Prompt Multi-View Vector Ensembling (AIC 2026).

Constructs a 4-view domain-adapted prompt composite to stabilize CLIP embedding variance:
    - Direct translated query (w=0.45)
    - Photo template: 'a clear photo of <query>' (w=0.25)
    - Broadcast news template: 'a television news footage showing <query>' (w=0.20)
    - Vietnamese scene template: 'a scene in Vietnam with <query>' (w=0.10)
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

PROMPT_TEMPLATES: list[tuple[str, float]] = [
    ("{text}", 0.45),
    ("a clear photo of {text}", 0.25),
    ("a television news broadcast footage showing {text}", 0.20),
    ("a street scene in Vietnam with {text}", 0.10),
]


def build_multi_prompt_variations(text: str) -> list[tuple[str, float]]:
    """Generate 4 domain-adapted prompt variations with associated weights."""
    cleaned = text.strip()
    if not cleaned:
        return [("", 1.0)]

    variations: list[tuple[str, float]] = []
    for tmpl, weight in PROMPT_TEMPLATES:
        rendered = tmpl.format(text=cleaned)
        variations.append((rendered, weight))

    return variations


def encode_multi_prompt_ensemble_vector(
    text: str,
    encoder_callable: Any,
) -> np.ndarray:
    """Encode a 4-view prompt ensemble and return a unit-normalized composite vector."""
    variations = build_multi_prompt_variations(text)
    texts = [v[0] for v in variations]
    weights = np.array([v[1] for v in variations], dtype=np.float32)

    try:
        # Batch encode all 4 variations simultaneously
        vectors = encoder_callable(texts)
        if isinstance(vectors, list) or not isinstance(vectors, np.ndarray):
            vectors = np.array(vectors, dtype=np.float32)

        # Weighted average
        weights_expanded = weights[:, np.newaxis]
        composite = np.sum(vectors * weights_expanded, axis=0) / np.sum(weights)

        # L2 normalize
        norm = float(np.linalg.norm(composite))
        if norm > 1e-6:
            composite = composite / norm

        return composite
    except Exception as exc:
        logger.warning("multi_prompt_ensemble_failed: %s, falling back to direct encode", exc)
        single = encoder_callable(text)
        if isinstance(single, list):
            single = np.array(single, dtype=np.float32)
        norm = float(np.linalg.norm(single))
        return single / norm if norm > 1e-6 else single
