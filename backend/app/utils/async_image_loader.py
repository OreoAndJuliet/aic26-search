"""Speculative Async Image Decoding & Memory Pre-Caching for VQA & Alignment."""

from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

logger = logging.getLogger(__name__)

# Fast thread-safe in-memory LRU cache for recently decoded PIL images
_DECODED_IMAGE_CACHE: dict[str, Image.Image] = {}
_CACHE_LOCK = threading.Lock()
_MAX_CACHE_SIZE = 256
_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="speculative_decoder")


def preload_image_async(image_path: Path) -> None:
    """Speculatively decode an image into RAM in background thread."""
    key = str(image_path)
    with _CACHE_LOCK:
        if key in _DECODED_IMAGE_CACHE:
            return
    if not image_path.is_file():
        return

    def _decode() -> None:
        try:
            with Image.open(image_path) as img:
                decoded = img.convert("RGB")
                with _CACHE_LOCK:
                    if len(_DECODED_IMAGE_CACHE) >= _MAX_CACHE_SIZE:
                        # Pop oldest item
                        try:
                            _DECODED_IMAGE_CACHE.pop(next(iter(_DECODED_IMAGE_CACHE)))
                        except (KeyError, StopIteration):
                            pass
                    _DECODED_IMAGE_CACHE[key] = decoded
        except Exception as exc:
            logger.debug("Speculative decode failed for %s: %s", image_path, exc)

    _EXECUTOR.submit(_decode)


def preload_images_batch(image_paths: list[Path]) -> None:
    """Preload a batch of candidate images asynchronously."""
    for p in image_paths:
        preload_image_async(p)


def get_cached_or_open_image(image_path: Path) -> Image.Image | None:
    """Retrieve preloaded image from RAM if available; otherwise open directly."""
    key = str(image_path)
    with _CACHE_LOCK:
        if key in _DECODED_IMAGE_CACHE:
            return _DECODED_IMAGE_CACHE[key]

    if not image_path.is_file():
        return None

    try:
        with Image.open(image_path) as img:
            decoded = img.convert("RGB")
            with _CACHE_LOCK:
                if len(_DECODED_IMAGE_CACHE) >= _MAX_CACHE_SIZE:
                    try:
                        _DECODED_IMAGE_CACHE.pop(next(iter(_DECODED_IMAGE_CACHE)))
                    except (KeyError, StopIteration):
                        pass
                _DECODED_IMAGE_CACHE[key] = decoded
            return decoded
    except Exception as exc:
        logger.warning("Failed opening image %s: %s", image_path, exc)
        return None


def clear_decoded_image_cache() -> None:
    """Clear in-memory decoded image cache."""
    with _CACHE_LOCK:
        _DECODED_IMAGE_CACHE.clear()
