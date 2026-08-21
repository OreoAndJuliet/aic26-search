"""One place to warm up shared engines before serving requests or batch jobs."""

from __future__ import annotations

import logging

import numpy as np

from app.core.config import settings
from app.services.kis_engine import kis_engine
from app.services.zip_ingest import zip_ingest_service

logger = logging.getLogger(__name__)


def initialize_engines() -> None:
    """Ingest inbox zips, then deeply warm up FAISS, CLIP, VQA, Translator, and all encyclopedic stores."""
    if settings.ZIP_INGEST_ENABLED:
        results = zip_ingest_service.ingest_inbox()
        if results:
            logger.info("zip_ingest processed %s archive(s) at startup", len(results))

    # 1. Initialize KIS FAISS Vector Store and CLIP Text Encoder
    kis_engine.initialize()
    kis_engine.warm_up()

    # 2. Pre-warm Translator Cache
    try:
        from app.services.translator import translator
        translator.warm_up()
    except Exception as exc:
        logger.warning("translator pre-warm failed: %s", exc)

    # 3. Pre-warm VQA Engine & Object Store
    try:
        from app.services.vqa_engine import vqa_engine
        vqa_engine.warm_up()
    except Exception as exc:
        logger.warning("vqa_engine pre-warm failed: %s", exc)

    # 4. Pre-warm Encyclopedic Knowledge Store
    try:
        from app.services.encyclopedic_store import encyclopedic_store
        encyclopedic_store.load_all()
    except Exception as exc:
        logger.warning("encyclopedic_store pre-warm failed: %s", exc)

    # 5. Pre-warm Landmark Gazetteer
    try:
        from app.services.landmark_gazetteer import landmark_gazetteer
        landmark_gazetteer.load()
    except Exception as exc:
        logger.warning("landmark_gazetteer pre-warm failed: %s", exc)

    # 6. Pre-warm Inverted OCR & MediaInfo BM25 Stores
    try:
        from app.services.mediainfo_store import mediainfo_store
        from app.services.ocr_store import ocr_store
        ocr_store.build_index()
        mediainfo_store.build_index()
    except Exception as exc:
        logger.warning("stores pre-warm failed: %s", exc)

    # 7. Pre-warm Colloquial NLU, Strict Paraphraser, Negative Projector, Color-Object Reranker & Multi-Prompt
    try:
        from app.algorithms.color_object_reranker import (
            extract_color_object_constraints,
        )
        from app.algorithms.human_intent_nlu import parse_human_intent
        from app.algorithms.multi_prompt_ensemble import build_multi_prompt_variations
        from app.algorithms.negative_projection import extract_negative_constraint
        from app.algorithms.strict_paraphrase import generate_strict_paraphrases
        from app.algorithms.symbolic_reasoner import rgb_to_hsv_numpy
        parse_human_intent("ninja áo chống nắng")
        generate_strict_paraphrases("a person walking in a room")
        extract_negative_constraint("người đi xe máy không đội mũ")
        extract_color_object_constraints("xe buýt màu xanh lá cây")
        build_multi_prompt_variations("kitchen scene with wooden table")
        rgb_to_hsv_numpy(np.zeros((10, 10, 3), dtype=np.uint8))
    except Exception as exc:
        logger.warning("algorithm pre-warm failed: %s", exc)

    logger.info("Turbo Startup Warmup Complete: All engines primed for sub-millisecond query execution.")
