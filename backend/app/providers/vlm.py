"""Vision-language provider abstractions for VQA."""

from __future__ import annotations

import base64
import json
from abc import ABC, abstractmethod
from pathlib import Path
from threading import local

import requests

from app.core.exceptions import VLMUnavailableError
from app.utils.circuit_breaker import (
    CircuitBreakerConfig,
)
from app.utils.vqa_answer import build_vqa_prompt


class VLMProvider(ABC):
    @abstractmethod
    def answer(self, image_path: Path, question: str) -> str:
        """Return raw provider text (preferably JSON with an answer field)."""


class MockVLMProvider(VLMProvider):
    def answer(self, image_path: Path, question: str) -> str:
        if not image_path.is_file():
            return ""
        
        # Extracted question from the prompt (e.g. "Question: how many cars are there?\nInstruction: ...")
        q_text = question
        if "Question:" in question:
            q_text = question.split("Question:")[1].split("\n")[0].strip()
            
        return f"Mock answer for: {q_text}"


class GeminiVLMProvider(VLMProvider):
    def __init__(self, api_key: str, model_name: str, timeout_seconds: float, api_base: str = "") -> None:
        if not api_key.strip():
            raise VLMUnavailableError("GEMINI_API_KEY is not configured.")
        if not model_name.strip():
            raise VLMUnavailableError("GEMINI_MODEL is not configured.")

        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise VLMUnavailableError(
                "Gemini VLM provider requires the google-genai package."
            ) from exc

        self._types = types
        if not api_base.strip():
            raise VLMUnavailableError("GEMINI_API_BASE is not configured.")
        self._api_base = api_base.strip()
        self._client = genai.Client(api_key=api_key)
        self._model = model_name.strip().strip('"').strip("'")
        self._model = self._model.removeprefix("models/")
        self._timeout_seconds = timeout_seconds
        
        # Initialize circuit breaker for Gemini API calls
        from app.utils.circuit_breaker import get_circuit_breaker
        self._circuit_breaker = get_circuit_breaker(
            "gemini_vlm",
            CircuitBreakerConfig(
                failure_threshold=5,
                recovery_timeout=60.0,
                expected_exception=(ConnectionError, TimeoutError, OSError, VLMUnavailableError),
                timeout=timeout_seconds
            )
        )

    def answer(self, image_path: Path, question: str) -> str:
        # Use circuit breaker for API call protection
        def _make_api_call():
            if not image_path.is_file():
                raise VLMUnavailableError(f"Image file not found: {image_path}")

            mime_type = "image/png" if image_path.suffix.lower() == ".png" else "image/jpeg"
            image_bytes = image_path.read_bytes()
            
            if len(image_bytes) == 0:
                raise VLMUnavailableError(f"Image file is empty: {image_path}")

            import time as _time
            max_retries = 4
            for attempt in range(max_retries):
                try:
                    response = self._client.models.generate_content(
                        model=self._model,
                        contents=[
                            build_vqa_prompt(question),
                            self._types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                        ],
                        config={
                            "temperature": 0.2,
                        },
                    )
                    break
                except (ConnectionError, TimeoutError, OSError) as exc:
                    if attempt < max_retries - 1:
                        _time.sleep(2 ** attempt)  # 1s, 2s, 4s
                        continue
                    raise VLMUnavailableError(f"Gemini VLM request failed due to network error: {exc}") from exc
                except Exception as exc:  # google-genai does not expose a stable hierarchy; noqa: BLE001
                    # Retry on 503 (overloaded) and 429 (rate limit) with backoff
                    exc_str = str(exc)
                    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
                    is_retryable = status in (503, 429) or "503" in exc_str or "429" in exc_str or "UNAVAILABLE" in exc_str or "RESOURCE_EXHAUSTED" in exc_str
                    if is_retryable and attempt < max_retries - 1:
                        wait = 2 ** attempt * 2  # 2s, 4s, 8s
                        import logging as _logging
                        _logging.getLogger(__name__).warning(
                            "Gemini transient error (attempt %d/%d), retrying in %ds: %s",
                            attempt + 1, max_retries, wait, exc_str[:120],
                        )
                        _time.sleep(wait)
                        continue
                    import traceback
                    error_details = traceback.format_exc()
                    raise VLMUnavailableError(f"Gemini VLM request failed. Error: {exc}. Details: {error_details}") from exc

            text = (response.text or "").strip()
            if not text:
                raise VLMUnavailableError("Gemini VLM returned an empty response.")
            
            return text
        
        # Execute with circuit breaker protection
        return self._circuit_breaker.call(_make_api_call)


class OpenAIVLMProvider(VLMProvider):
    def __init__(self, api_key: str, model_name: str, timeout_seconds: float, api_base: str = "") -> None:
        if not api_key.strip():
            raise VLMUnavailableError("OPENAI_API_KEY is not configured.")
        if not model_name.strip():
            raise VLMUnavailableError("OPENAI_VQA_MODEL is not configured.")

        self._api_key = api_key
        self._model_name = model_name.strip()
        if not api_base.strip():
            raise VLMUnavailableError("OPENAI_API_BASE is not configured.")
        self._api_base = api_base.strip()
        self._timeout_seconds = timeout_seconds
        self._thread_local = local()

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

    def answer(self, image_path: Path, question: str) -> str:
        if not image_path.is_file():
            return json.dumps({"answer": ""})

        mime_type = "image/png" if image_path.suffix.lower() == ".png" else "image/jpeg"
        encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
        payload = {
            "model": self._model_name,
            "temperature": 0.2,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": build_vqa_prompt(question)},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{encoded}",
                            },
                        },
                    ],
                }
            ],
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        try:
            response = self._session().post(
                f"{self._api_base}/v1/chat/completions",
                headers=headers,
                data=json.dumps(payload),
                timeout=self._timeout_seconds,
            )
            response.raise_for_status()
            data = response.json()
            text = data["choices"][0]["message"]["content"].strip()
        except requests.Timeout as exc:
            raise VLMUnavailableError("OpenAI VLM request timed out.") from exc
        except (requests.RequestException, KeyError, IndexError, TypeError, ValueError) as exc:
            raise VLMUnavailableError("OpenAI VLM request failed.") from exc

        if not text:
            raise VLMUnavailableError("OpenAI VLM returned an empty response.")
        return text


class ClaudeVLMProvider(VLMProvider):
    def __init__(self, api_key: str, model_name: str, timeout_seconds: float, api_base: str = "") -> None:
        if not api_key.strip():
            raise VLMUnavailableError("ANTHROPIC_API_KEY is not configured.")
        if not model_name.strip():
            raise VLMUnavailableError("CLAUDE_VQA_MODEL is not configured.")

        self._api_key = api_key
        self._model_name = model_name.strip()
        if not api_base.strip():
            raise VLMUnavailableError("ANTHROPIC_API_BASE is not configured.")
        self._api_base = api_base.strip()
        self._timeout_seconds = timeout_seconds
        self._thread_local = local()

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

    def answer(self, image_path: Path, question: str) -> str:
        if not image_path.is_file():
            return json.dumps({"answer": ""})

        mime_type = "image/png" if image_path.suffix.lower() == ".png" else "image/jpeg"
        encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
        payload = {
            "model": self._model_name,
            "max_tokens": 256,
            "temperature": 0.2,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": mime_type,
                                "data": encoded,
                            },
                        },
                        {"type": "text", "text": build_vqa_prompt(question)},
                    ],
                }
            ],
        }
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        try:
            response = self._session().post(
                f"{self._api_base}/v1/messages",
                headers=headers,
                data=json.dumps(payload),
                timeout=self._timeout_seconds,
            )
            response.raise_for_status()
            data = response.json()
            parts = data.get("content", [])
            text = "".join(part.get("text", "") for part in parts if part.get("type") == "text")
            text = text.strip()
        except requests.Timeout as exc:
            raise VLMUnavailableError("Claude VLM request timed out.") from exc
        except (requests.RequestException, KeyError, TypeError, ValueError) as exc:
            raise VLMUnavailableError("Claude VLM request failed.") from exc

        if not text:
            raise VLMUnavailableError("Claude VLM returned an empty response.")
        return text


class QwenVLMProvider(VLMProvider):
    """Qwen-VL via OpenAI-compatible DashScope endpoint."""

    def __init__(
        self,
        api_key: str,
        model_name: str,
        api_base: str,
        timeout_seconds: float,
    ) -> None:
        if not api_key.strip():
            raise VLMUnavailableError("QWEN_API_KEY is not configured.")
        if not model_name.strip():
            raise VLMUnavailableError("QWEN_VQA_MODEL is not configured.")

        self._api_key = api_key
        self._model_name = model_name.strip()
        self._api_base = api_base.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._thread_local = local()

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

    def answer(self, image_path: Path, question: str) -> str:
        if not image_path.is_file():
            return json.dumps({"answer": ""})

        mime_type = "image/png" if image_path.suffix.lower() == ".png" else "image/jpeg"
        encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
        payload = {
            "model": self._model_name,
            "temperature": 0.2,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": build_vqa_prompt(question)},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{encoded}",
                            },
                        },
                    ],
                }
            ],
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        try:
            response = self._session().post(
                f"{self._api_base}/chat/completions",
                headers=headers,
                data=json.dumps(payload),
                timeout=self._timeout_seconds,
            )
            response.raise_for_status()
            data = response.json()
            text = data["choices"][0]["message"]["content"].strip()
        except requests.Timeout as exc:
            raise VLMUnavailableError("Qwen VLM request timed out.") from exc
        except (requests.RequestException, KeyError, IndexError, TypeError, ValueError) as exc:
            raise VLMUnavailableError("Qwen VLM request failed.") from exc

        if not text:
            raise VLMUnavailableError("Qwen VLM returned an empty response.")
        return text


def create_vlm_provider(
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
    anthropic_api_key: str = "",
    claude_model_name: str = "",
    anthropic_api_base: str = "",
    qwen_api_key: str = "",
    qwen_model_name: str = "",
    qwen_api_base: str = "",
) -> VLMProvider:
    normalized_mode = provider_mode.strip().lower()
    if normalized_mode == "mock":
        return MockVLMProvider()

    normalized_provider = provider_name.strip().lower()
    if normalized_provider == "gemini":
        return GeminiVLMProvider(gemini_api_key, gemini_model_name, timeout_seconds, gemini_api_base)
    if normalized_provider == "openai":
        return OpenAIVLMProvider(openai_api_key, openai_model_name, timeout_seconds, openai_api_base)
    if normalized_provider == "claude":
        return ClaudeVLMProvider(anthropic_api_key, claude_model_name, timeout_seconds, anthropic_api_base)
    if normalized_provider == "qwen":
        return QwenVLMProvider(
            qwen_api_key,
            qwen_model_name,
            qwen_api_base or "https://dashscope.aliyuncs.com/compatible-mode/v1",
            timeout_seconds,
        )
    raise VLMUnavailableError(f"Unsupported VQA provider: {provider_name}.")



