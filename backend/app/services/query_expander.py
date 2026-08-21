"""Visual paraphrasing and multi-query expansion for KIS & VQA video retrieval."""

from __future__ import annotations

import json
import logging
from typing import Any

from app.cache.factory import create_cache_backend
from app.core.config import settings

logger = logging.getLogger(__name__)


class QueryExpanderService:
    """Expands queries into multiple visual descriptions to boost retrieval recall."""

    def __init__(self) -> None:
        self._cache_backend = create_cache_backend(namespace="query_expansion")
        self._ttl_seconds = settings.QUERY_EXPANSION_CACHE_TTL_SECONDS
        self._gemini_client: Any = None
        self._gemini_initialized = False

    def _get_gemini_client(self) -> Any:
        if self._gemini_initialized:
            return self._gemini_client

        self._gemini_initialized = True
        api_key = settings.GEMINI_API_KEY.strip()
        if not api_key or settings.AI_PROVIDER_MODE.strip().lower() == "mock":
            return None

        try:
            from google import genai
            self._gemini_client = genai.Client(api_key=api_key)
        except Exception as exc:
            logger.warning("query_expander gemini_client_init_failed: %s", exc)
            self._gemini_client = None

        return self._gemini_client

    def _cache_key(self, query: str, mode: str) -> str:
        import hashlib
        return f"{mode}:{hashlib.sha256(query.strip().casefold().encode('utf-8')).hexdigest()}"

    def _get_cached(self, query: str, mode: str) -> list[str] | None:
        key = self._cache_key(query, mode)
        try:
            raw = self._cache_backend.get(key)
            if raw is not None:
                return json.loads(raw.decode("utf-8"))
        except Exception:
            pass
        return None

    def _set_cached(self, query: str, mode: str, variations: list[str]) -> None:
        key = self._cache_key(query, mode)
        try:
            payload = json.dumps(variations).encode("utf-8")
            self._cache_backend.set(key, payload, ttl_seconds=self._ttl_seconds)
        except Exception:
            pass

    def _expand_with_templates(self, query: str, num_variations: int = 4) -> list[str]:
        """Generate visual template descriptions for zero-latency offline expansion.
        
        Templates are optimized for the AIC dataset which consists primarily of
        Vietnamese news broadcast video keyframes.
        """
        clean_q = query.strip()
        templates = [
            f"a photo of {clean_q}",
            f"a video frame showing {clean_q}",
            f"Vietnamese news broadcast showing {clean_q}",
            f"outdoor scene with {clean_q}",
            f"a clear image of {clean_q}",
            f"a close-up of {clean_q}",
        ]
        return templates[:num_variations]

    def _expand_with_llm(self, query: str, num_variations: int = 3) -> list[str]:
        """Generate diverse visual descriptions using Gemini."""
        client = self._get_gemini_client()
        if client is None:
            return self._expand_with_templates(query, num_variations)

        prompt = (
            "You are an expert visual search engine assistant for video keyframe retrieval. "
            f"Given the user search query, generate {num_variations} diverse, concrete visual descriptions in English "
            "describing what a matching video frame would look like. "
            "Focus on visible objects, colors, settings, and physical actions. Keep each description concise (5-15 words).\n"
            "Return ONLY a JSON array of strings, e.g. [\"desc 1\", \"desc 2\", \"desc 3\"].\n\n"
            f"Query: {query}"
        )

        try:
            model_name = settings.GEMINI_MODEL.strip().strip('"').strip("'").removeprefix("models/")
            response = client.models.generate_content(
                model=model_name,
                contents=[prompt],
                config={
                    "temperature": 0.3,
                    "response_mime_type": "application/json",
                },
            )
            text = (response.text or "").strip()
            if text:
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    return [str(item).strip() for item in parsed if str(item).strip()][:num_variations]
        except Exception as exc:
            logger.warning("query_expander llm_expansion_failed for '%s': %s", query, exc)

        return self._expand_with_templates(query, num_variations)

    def expand_query(self, query: str) -> list[str]:
        """
        Return a list of visual query strings: [original_query, variation_1, variation_2, ...].
        """
        clean_q = query.strip()
        if not clean_q or not settings.QUERY_EXPANSION_ENABLED:
            return [clean_q] if clean_q else []

        mode = settings.QUERY_EXPANSION_MODE.strip().lower()
        if mode == "off":
            return [clean_q]

        cached = self._get_cached(clean_q, mode)
        if cached is not None:
            return cached

        num_vars = settings.QUERY_EXPANSION_NUM_VARIATIONS
        variations: list[str] = [clean_q]

        if mode == "llm":
            llm_vars = self._expand_with_llm(clean_q, num_vars)
            for v in llm_vars:
                if v and v.casefold() != clean_q.casefold() and v not in variations:
                    variations.append(v)
        elif mode == "template":
            tmpl_vars = self._expand_with_templates(clean_q, num_vars)
            for v in tmpl_vars:
                if v and v.casefold() != clean_q.casefold() and v not in variations:
                    variations.append(v)
        elif mode == "hybrid":
            llm_vars = self._expand_with_llm(clean_q, max(num_vars - 1, 1))
            tmpl_vars = self._expand_with_templates(clean_q, 1)
            for v in llm_vars + tmpl_vars:
                if v and v.casefold() != clean_q.casefold() and v not in variations:
                    variations.append(v)

        result = variations[: num_vars + 1]
        self._set_cached(clean_q, mode, result)
        logger.info("query_expanded original='%s' variations=%s", clean_q, result)
        return result


query_expander = QueryExpanderService()
