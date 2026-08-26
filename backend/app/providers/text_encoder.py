import hashlib
import logging
import os
import warnings
from abc import ABC, abstractmethod
from pathlib import Path

# Suppress PIL warnings about image processor speed BEFORE any imports
os.environ["USE_FAST"] = "1"
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
warnings.filterwarnings("ignore", message=".*use_fast.*")
warnings.filterwarnings("ignore", message=".*slow processor.*")

import numpy as np

from app.core.exceptions import RetrievalUnavailableError

logger = logging.getLogger(__name__)


class TextEncoder(ABC):
    """CPU/GPU-bound query encoder for the image-feature embedding space."""

    @abstractmethod
    def encode(self, text: str) -> np.ndarray:
        """Return one L2-normalized float32 embedding for text."""

    def encode_batch(self, texts: list[str]) -> np.ndarray:
        """Return a batch of L2-normalized float32 embeddings for a list of texts."""
        if not texts:
            return np.empty((0, 512), dtype=np.float32)
        return np.vstack([self.encode(t) for t in texts])

    def encode_image(self, image_path: Path) -> np.ndarray:
        """Return one L2-normalized float32 embedding for an image file."""
        raise RetrievalUnavailableError(
            f"{self.__class__.__name__} does not support image encoding."
        )


class SentenceTransformerClipTextEncoder(TextEncoder):
    """CLIP-compatible encoder isolated from retrieval orchestration."""

    def __init__(self, model_name: str) -> None:
        try:
            import torch
            from sentence_transformers import SentenceTransformer

            device = "cuda" if torch.cuda.is_available() else "cpu"
            self._model = SentenceTransformer(
                model_name,
                device=device,
                model_kwargs={"low_cpu_mem_usage": True},
            )
            self.provider_name = "sentence_transformers"
            self.device = device
        except (ImportError, OSError, RuntimeError) as exc:
            raise RetrievalUnavailableError("Unable to load the configured text encoder.") from exc

    def encode(self, text: str) -> np.ndarray:
        import os
        import sys
        old_stderr = sys.stderr
        text = " ".join(text.split()[:30])
        with open(os.devnull, "w") as devnull:
            sys.stderr = devnull
            try:
                vector = self._model.encode(
                    [text],
                    show_progress_bar=False,
                    normalize_embeddings=True,
                    convert_to_numpy=True,
                ).astype(np.float32, copy=False)
            finally:
                sys.stderr = old_stderr
        if vector.shape[0] != 1:
            raise RetrievalUnavailableError("The text encoder returned an invalid embedding batch.")
        vector.setflags(write=False)
        return vector

    def encode_batch(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, 512), dtype=np.float32)
        import os
        import sys
        old_stderr = sys.stderr
        texts = [" ".join(t.split()[:30]) for t in texts]
        with open(os.devnull, "w") as devnull:
            sys.stderr = devnull
            try:
                vectors = self._model.encode(
                    texts,
                    show_progress_bar=False,
                    normalize_embeddings=True,
                    convert_to_numpy=True,
                ).astype(np.float32, copy=False)
            finally:
                sys.stderr = old_stderr
        return vectors

    def encode_image(self, image_path: Path) -> np.ndarray:
        try:
            from PIL import Image
        except ImportError as exc:
            raise RetrievalUnavailableError("Pillow is required for image encoding.") from exc

        import os
        import sys
        old_stderr = sys.stderr

        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message=".*use_fast.*")
            with Image.open(image_path) as image:
                with open(os.devnull, "w") as devnull:
                    sys.stderr = devnull
                    try:
                        vector = self._model.encode(
                            [image],
                            show_progress_bar=False,
                            normalize_embeddings=True,
                            convert_to_numpy=True,
                        ).astype(np.float32, copy=False)
                    finally:
                        sys.stderr = old_stderr
        if vector.shape[0] != 1:
            raise RetrievalUnavailableError("The text encoder returned an invalid image batch.")
        vector.setflags(write=False)
        return vector


class MockTextEncoder(TextEncoder):
    """Deterministic mock encoder for local testing without external model loads."""

    def __init__(self, dimension: int, *, seed_offset: int = 0) -> None:
        if dimension <= 0:
            raise RetrievalUnavailableError("Mock text encoder dimension must be positive.")
        self._dimension = dimension
        self._seed_offset = seed_offset
        self.provider_name = "mock"
        self.device = "cpu"

    def encode(self, text: str) -> np.ndarray:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        seed = int.from_bytes(digest[:8], byteorder="big", signed=False) + self._seed_offset
        rng = np.random.default_rng(seed)
        vector = rng.standard_normal((1, self._dimension)).astype(np.float32, copy=False)
        norm = np.linalg.norm(vector, axis=1, keepdims=True)
        if float(norm[0, 0]) == 0.0:
            raise RetrievalUnavailableError("Mock text encoder produced a zero vector.")
        vector /= norm
        vector.setflags(write=False)
        return vector


class EnsembleTextEncoder(TextEncoder):
    """Weighted average of multiple normalized encoders (CLIP + SigLIP, etc.)."""

    def __init__(
        self,
        encoders: list[tuple[TextEncoder, float]],
    ) -> None:
        if not encoders:
            raise RetrievalUnavailableError("Ensemble text encoder requires at least one model.")
        total_weight = sum(weight for _, weight in encoders)
        if total_weight <= 0:
            raise RetrievalUnavailableError("Ensemble weights must sum to a positive value.")

        self._encoders = [(encoder, weight / total_weight) for encoder, weight in encoders]
        self.provider_name = "ensemble"
        self.device = self._encoders[0][0].device

    def encode(self, text: str) -> np.ndarray:
        combined = None
        for encoder, weight in self._encoders:
            vector = encoder.encode(text).astype(np.float32, copy=False).reshape(-1)
            weighted = vector * weight
            combined = weighted if combined is None else combined + weighted

        if combined is None:
            raise RetrievalUnavailableError("Ensemble text encoder failed to produce combined vector")
        norm = float(np.linalg.norm(combined))
        if norm == 0.0:
            raise RetrievalUnavailableError("Ensemble text encoder produced a zero vector.")
        combined /= norm
        return combined.reshape(1, -1)


def create_text_encoder(
    provider: str,
    model_name: str,
    mock_dimension: int = 512,
    *,
    ensemble_enabled: bool = False,
    ensemble_model_name: str = "",
    ensemble_primary_weight: float = 0.5,
    ensemble_secondary_weight: float = 0.5,
    fallback_to_mock: bool = True,
) -> TextEncoder:
    normalized_provider = provider.strip().lower()
    if normalized_provider == "sentence_transformers":
        try:
            primary = SentenceTransformerClipTextEncoder(model_name)
        except RetrievalUnavailableError:
            if fallback_to_mock:
                logger.warning(
                    "SentenceTransformer text encoder failed to load; falling back to mock encoder. "
                    "Set TEXT_ENCODER_PROVIDER=mock or install the model on this machine."
                )
                return MockTextEncoder(mock_dimension)
            raise
        if ensemble_enabled and ensemble_model_name.strip():
            try:
                secondary = SentenceTransformerClipTextEncoder(ensemble_model_name.strip())
            except RetrievalUnavailableError:
                if fallback_to_mock:
                    logger.warning(
                        "Secondary ensemble encoder failed to load; falling back to primary mock encoder."
                    )
                    return MockTextEncoder(mock_dimension)
                raise
            return EnsembleTextEncoder(
                [
                    (primary, ensemble_primary_weight),
                    (secondary, ensemble_secondary_weight),
                ]
            )
        return primary
    if normalized_provider == "mock":
        if ensemble_enabled:
            return EnsembleTextEncoder(
                [
                    (MockTextEncoder(mock_dimension, seed_offset=0), ensemble_primary_weight),
                    (MockTextEncoder(mock_dimension, seed_offset=1), ensemble_secondary_weight),
                ]
            )
        return MockTextEncoder(mock_dimension)
    raise RetrievalUnavailableError(f"Unsupported text encoder provider: {provider}.")
