import asyncio
from abc import ABC, abstractmethod
from functools import lru_cache
from threading import local

import requests

from app.core.exceptions import TranslationUnavailableError
from app.utils.circuit_breaker import (
    CircuitBreakerConfig,
    get_circuit_breaker,
)


def _translation_prompt(text: str, source_language: str, target_language: str) -> str:
    return (
        "Translate the following user query from "
        f"{source_language} to {target_language}. "
        "Preserve names and proper nouns. Return only the translated query text.\n\n"
        f"Query: {text}"
    )


class TranslationProvider(ABC):
    @abstractmethod
    async def translate(
        self, text: str, source_language: str, target_language: str
    ) -> str:
        """Translate one query string."""


class NoOpTranslationProvider(TranslationProvider):
    async def translate(
        self, text: str, source_language: str, target_language: str
    ) -> str:
        return text


class MockTranslationProvider(TranslationProvider):
    async def translate(
        self, text: str, source_language: str, target_language: str
    ) -> str:
        return text


# Module-level cached helper to avoid decorating instance methods with lru_cache
@lru_cache(maxsize=512)
def _google_gtx_translate_cached(text: str, timeout_seconds: float, api_base: str) -> str:
    session = requests.Session()
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    translated = ""

    # Cap the timeout per strategy to ensure the fallback chain executes quickly
    req_timeout = min(timeout_seconds, 1.5)

    # Strategy 1: Google Clients5 Chrome Extension API (High throughput, no 429)
    try:
        response = session.get(
            "https://clients5.google.com/translate_a/t",
            params={"client": "dict-chrome-ex", "sl": "vi", "tl": "en", "q": text},
            headers=headers,
            timeout=req_timeout,
        )
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list) and data:
                translated = str(data[0]).strip()
    except Exception:
        pass

    # Strategy 2: Google GTX Web Single Endpoint (Default fallback)
    if not translated:
        try:
            response = session.get(
                f"{api_base}/translate_a/single",
                params={"client": "gtx", "sl": "vi", "tl": "en", "dt": "t", "q": text},
                headers=headers,
                timeout=req_timeout,
            )
            if response.status_code == 200:
                result = response.json()
                translated = "".join(item[0] for item in result[0] if item and item[0]).strip()
        except Exception:
            pass

    # Strategy 3: MyMemory Translation API fallback
    if not translated:
        try:
            response = session.get(
                f"https://api.mymemory.translated.net/get?q={requests.utils.quote(text)}&langpair=vi|en",
                timeout=req_timeout,
            )
            if response.status_code == 200:
                res = response.json()
                t_text = res.get("responseData", {}).get("translatedText", "")
                if t_text:
                    translated = t_text.strip()
        except Exception:
            pass

    session.close()

    if not translated:
        raise TranslationUnavailableError("Translation provider returned empty text.")
    return translated


class GoogleGtxTranslationProvider(TranslationProvider):
    def __init__(self, timeout_seconds: float, api_base: str = "") -> None:
        self._thread_local = local()
        self._timeout_seconds = timeout_seconds
        if not api_base.strip():
            raise TranslationUnavailableError("GOOGLE_TRANSLATION_API_BASE is not configured.")
        self._api_base = api_base.strip()
        
        # Initialize circuit breaker for Google translation API
        self._circuit_breaker = get_circuit_breaker(
            "google_gtx_translation",
            CircuitBreakerConfig(
                failure_threshold=3,
                recovery_timeout=30.0,
                expected_exception=(requests.Timeout, requests.RequestException, TranslationUnavailableError),
                timeout=timeout_seconds
            )
        )

    def _session(self) -> requests.Session:
        session = getattr(self._thread_local, "session", None)
        if session is None:
            session = requests.Session()
            self._thread_local.session = session
        return session

    def close(self) -> None:
        """Clean up HTTP session resources."""
        try:
            session = getattr(self._thread_local, "session", None)
            if session is not None:
                session.close()
                self._thread_local.session = None
        except AttributeError:
            # Handle case where __del__ is called before initialization completes
            pass

    def __del__(self) -> None:
        """Ensure session cleanup on object destruction."""
        self.close()

    def _translate_sync(self, text: str) -> str:
        # Use circuit breaker for API call protection
        def _make_api_call():
            # Use the module-level cached translator so caching is safe and not bound to instance lifetimes
            return _google_gtx_translate_cached(text, self._timeout_seconds, self._api_base)
        
        # Execute with circuit breaker protection
        return self._circuit_breaker.call(_make_api_call)

    def clear_cache(self) -> None:
        """Clear the LRU cache to prevent memory leaks."""
        _google_gtx_translate_cached.cache_clear()  # type: ignore[attr-defined]

    async def translate(
        self, text: str, source_language: str, target_language: str
    ) -> str:
        return await asyncio.to_thread(self._translate_sync, text)


class GeminiTranslationProvider(TranslationProvider):
    def __init__(self, api_key: str, model_name: str, timeout_seconds: float, api_base: str = "") -> None:
        if not api_key.strip():
            raise TranslationUnavailableError("GEMINI_API_KEY is not configured.")
        self._api_key = api_key
        self._model_name = model_name
        if not api_base.strip():
            raise TranslationUnavailableError("GEMINI_TRANSLATION_API_BASE is not configured.")
        self._api_base = api_base.strip()
        self._thread_local = local()
        self._timeout_seconds = timeout_seconds

    def clear_cache(self) -> None:
        """Clear the LRU cache to prevent memory leaks (no-op for this provider)."""

    def _session(self) -> requests.Session:
        session = getattr(self._thread_local, "session", None)
        if session is None:
            session = requests.Session()
            self._thread_local.session = session
        return session

    def close(self) -> None:
        """Clean up HTTP session resources."""
        try:
            session = getattr(self._thread_local, "session", None)
            if session is not None:
                session.close()
                self._thread_local.session = None
        except AttributeError:
            # Handle case where __del__ is called before initialization completes
            pass

    def __del__(self) -> None:
        """Ensure session cleanup on object destruction."""
        self.close()

    def _translate_sync(self, text: str, source_language: str, target_language: str) -> str:
        prompt = _translation_prompt(text, source_language, target_language)
        url = (
            f"{self._api_base}/v1beta/models/"
            f"{self._model_name}:generateContent?key={self._api_key}"
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.0},
        }

        try:
            response = self._session().post(url, json=payload, timeout=self._timeout_seconds)
            response.raise_for_status()
            data = response.json()
            candidates = data["candidates"]
            translated = candidates[0]["content"]["parts"][0]["text"].strip()
        except requests.Timeout as exc:
            raise TranslationUnavailableError("Translation provider request timed out.") from exc
        except (requests.RequestException, KeyError, IndexError, TypeError, ValueError) as exc:
            raise TranslationUnavailableError("Translation provider request failed.") from exc

        if not translated:
            raise TranslationUnavailableError("Translation provider returned empty text.")
        return translated

    async def translate(
        self, text: str, source_language: str, target_language: str
    ) -> str:
        return await asyncio.to_thread(
            self._translate_sync,
            text,
            source_language,
            target_language,
        )


class OpenAITranslationProvider(TranslationProvider):
    def __init__(self, api_key: str, model_name: str, timeout_seconds: float, api_base: str = "") -> None:
        if not api_key.strip():
            raise TranslationUnavailableError("OPENAI_API_KEY is not configured.")
        self._api_key = api_key
        self._model_name = model_name
        if not api_base.strip():
            raise TranslationUnavailableError("OPENAI_TRANSLATION_API_BASE is not configured.")
        self._api_base = api_base.strip()
        self._thread_local = local()
        self._timeout_seconds = timeout_seconds

    def clear_cache(self) -> None:
        """Clear the LRU cache to prevent memory leaks (no-op for this provider)."""

    def _session(self) -> requests.Session:
        session = getattr(self._thread_local, "session", None)
        if session is None:
            session = requests.Session()
            self._thread_local.session = session
        return session

    def close(self) -> None:
        """Clean up HTTP session resources."""
        try:
            session = getattr(self._thread_local, "session", None)
            if session is not None:
                session.close()
                self._thread_local.session = None
        except AttributeError:
            # Handle case where __del__ is called before initialization completes
            pass

    def __del__(self) -> None:
        """Ensure session cleanup on object destruction."""
        self.close()

    def _translate_sync(self, text: str, source_language: str, target_language: str) -> str:
        prompt = _translation_prompt(text, source_language, target_language)
        # Use standard /v1/chat/completions endpoint (compatible with all OpenAI deployments)
        payload = {
            "model": self._model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        try:
            response = self._session().post(
                f"{self._api_base}/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=self._timeout_seconds,
            )
            response.raise_for_status()
            data = response.json()
            translated = data["choices"][0]["message"]["content"].strip()
        except requests.Timeout as exc:
            raise TranslationUnavailableError("Translation provider request timed out.") from exc
        except (requests.RequestException, KeyError, IndexError, TypeError, ValueError) as exc:
            raise TranslationUnavailableError("Translation provider request failed.") from exc

        if not translated:
            raise TranslationUnavailableError("Translation provider returned empty text.")
        return translated

    async def translate(
        self, text: str, source_language: str, target_language: str
    ) -> str:
        return await asyncio.to_thread(
            self._translate_sync,
            text,
            source_language,
            target_language,
        )


def create_translation_provider(
    *,
    provider_name: str,
    provider_mode: str,
    timeout_seconds: float,
    gemini_api_key: str,
    gemini_model_name: str,
    gemini_api_base: str = "",
    openai_api_key: str,
    openai_model_name: str,
    openai_api_base: str = "",
    google_translation_api_base: str = "",
) -> TranslationProvider:
    normalized_mode = provider_mode.strip().lower()
    if normalized_mode == "mock":
        return MockTranslationProvider()

    normalized_provider = provider_name.strip().lower()
    if normalized_provider in {"noop", "no_op"}:
        return NoOpTranslationProvider()
    if normalized_provider in {"google_gtx", "google"}:
        return GoogleGtxTranslationProvider(timeout_seconds, google_translation_api_base)
    if normalized_provider == "gemini":
        return GeminiTranslationProvider(gemini_api_key, gemini_model_name, timeout_seconds, gemini_api_base)
    if normalized_provider == "openai":
        return OpenAITranslationProvider(openai_api_key, openai_model_name, timeout_seconds, openai_api_base)
    raise TranslationUnavailableError(f"Unsupported translation provider: {provider_name}.")
