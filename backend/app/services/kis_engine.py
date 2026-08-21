import logging
import time
from pathlib import Path
from threading import Lock

import numpy as np

from app.cache.embedding_cache import EmbeddingCache
from app.cache.factory import create_cache_backend
from app.core.config import settings
from app.core.exceptions import DatasetValidationError, RetrievalUnavailableError
from app.providers.text_encoder import TextEncoder, create_text_encoder
from app.utils.validation import validated_kis_result
from app.vector.base import KeyframeVectorStore
from app.vector.factory import create_vector_store

logger = logging.getLogger(__name__)


class KISEngine:
    """Orchestrates text encoding, FAISS retrieval, and result validation."""

    def __init__(self) -> None:
        self._text_encoder: TextEncoder | None = None
        self._store: KeyframeVectorStore | None = None
        self._startup_error: str | None = None
        self._load_lock = Lock()
        self._embedding_cache = EmbeddingCache(
            create_cache_backend(namespace="embedding"),
            scope=self._embedding_cache_scope(),
            ttl_seconds=self._embedding_cache_ttl(),
        )

    @staticmethod
    def _embedding_cache_scope() -> str:
        parts = [
            settings.TEXT_ENCODER_PROVIDER,
            settings.CLIP_MODEL_NAME,
            str(settings.MOCK_EMBEDDING_DIM),
        ]
        if settings.TEXT_ENCODER_ENSEMBLE_ENABLED:
            parts.extend(
                [
                    "ensemble",
                    settings.ENSEMBLE_MODEL_NAME,
                    str(settings.ENSEMBLE_PRIMARY_WEIGHT),
                    str(settings.ENSEMBLE_SECONDARY_WEIGHT),
                ]
            )
        return ":".join(parts)

    @staticmethod
    def _embedding_cache_ttl() -> int | None:
        ttl = settings.EMBEDDING_CACHE_TTL_SECONDS
        return ttl if ttl > 0 else None

    @property
    def stats(self):
        if self._store is None:
            raise RetrievalUnavailableError(self._startup_error or "KIS is not initialized.")
        return self._store.stats

    @property
    def store(self) -> KeyframeVectorStore:
        if self._store is None:
            raise RetrievalUnavailableError(self._startup_error or "KIS is not initialized.")
        return self._store

    def resolve_keyframe_path(self, video_id: str, frame_id: int) -> Path | None:
        if self._store is None:
            return None
        return self._store.image_path_for_frame(video_id, frame_id)

    @property
    def text_encoder(self) -> TextEncoder:
        if self._text_encoder is None:
            raise RetrievalUnavailableError(self._startup_error or "KIS is not initialized.")
        return self._text_encoder

    def encode_query_vector(self, text: str) -> np.ndarray:
        if self._store is None or self._text_encoder is None:
            raise RetrievalUnavailableError(self._startup_error or "KIS is not initialized.")
        return self._encode_with_cache(text)[0].copy().reshape(-1)

    def initialize(self) -> None:
        """Load and validate the one shared index, mapping, and text encoder."""
        with self._load_lock:
            if self._store is not None and self._text_encoder is not None:
                return
            try:
                self._store = create_vector_store()
                # Load the text encoder during initialization to avoid first-request latency
                self._ensure_text_encoder_loaded()
                self.warm_up()
                self._startup_error = None
            except (DatasetValidationError, RetrievalUnavailableError) as exc:
                # Ensure complete cleanup of all resources on failure
                self._store = None
                self._text_encoder = None
                self._startup_error = str(exc) or "KIS retrieval is unavailable; inspect server logs."
                raise RetrievalUnavailableError(self._startup_error) from exc
            except Exception as exc:
                # Catch-all to avoid leaving KIS in a partially-initialized state
                self._store = None
                self._text_encoder = None
                self._startup_error = f"Unexpected initialization error: {exc}"
                logger.exception("kis_engine initialization failed with unexpected error")
                raise RetrievalUnavailableError(self._startup_error) from exc

    def reload_index(self) -> None:
        """Reload the vector store (FAISS index and metadata) from disk without dropping the text encoder."""
        with self._load_lock:
            try:
                self._store = create_vector_store()
                self._startup_error = None
                self.warm_up()
                logger.info("Successfully reloaded vector index and metadata.")
            except (DatasetValidationError, RetrievalUnavailableError) as exc:
                self._store = None
                self._startup_error = str(exc)
                logger.error("Failed to reload vector index: %s", exc)
                raise RetrievalUnavailableError(self._startup_error) from exc

    def _ensure_text_encoder_loaded(self) -> None:
        if self._text_encoder is not None:
            return
        logger.info("loading_text_encoder provider=%s", settings.TEXT_ENCODER_PROVIDER)
        self._text_encoder = create_text_encoder(
            settings.TEXT_ENCODER_PROVIDER,
            settings.CLIP_MODEL_NAME,
            settings.MOCK_EMBEDDING_DIM,
            ensemble_enabled=settings.TEXT_ENCODER_ENSEMBLE_ENABLED,
            ensemble_model_name=settings.ENSEMBLE_MODEL_NAME,
            ensemble_primary_weight=settings.ENSEMBLE_PRIMARY_WEIGHT,
            ensemble_secondary_weight=settings.ENSEMBLE_SECONDARY_WEIGHT,
            fallback_to_mock=settings.TEXT_ENCODER_FALLBACK_TO_MOCK,
        )

    def _encode_with_cache(self, text: str) -> tuple[np.ndarray, bool]:
        # Ensure the text encoder is loaded lazily to avoid heavy imports during
        # initialize() when only FAISS index is required. This also centralizes
        # encoder creation errors so they can be transformed to RetrievalUnavailableError.
        if self._text_encoder is None:
            try:
                self._ensure_text_encoder_loaded()
            except RetrievalUnavailableError:
                # Re-raise so callers handle this uniformly
                raise
            except Exception as exc:
                raise RetrievalUnavailableError(f"Failed to load text encoder: {exc}") from exc

        cached = self._embedding_cache.get(text)
        if cached is not None:
            return cached, True

        from app.algorithms.concept_decomposition import build_multiconcept_fused_vector
        from app.services.query_expander import query_expander

        # 1. Multi-concept semantic decomposition
        if settings.MULTI_CONCEPT_DECOMPOSITION_ENABLED:
            try:
                primary_vec = build_multiconcept_fused_vector(
                    text,
                    self._text_encoder,
                    w_global=settings.MULTI_CONCEPT_WEIGHT_GLOBAL,
                    w_entity=settings.MULTI_CONCEPT_WEIGHT_ENTITY,
                    w_attribute=settings.MULTI_CONCEPT_WEIGHT_ATTRIBUTE,
                    w_action=settings.MULTI_CONCEPT_WEIGHT_ACTION,
                    w_scene=settings.MULTI_CONCEPT_WEIGHT_SCENE,
                ).astype(np.float32, copy=False).reshape(-1)
            except Exception as exc:
                logger.warning("multiconcept_decomposition_failed: %s", exc)
                primary_vec = self._text_encoder.encode(text).astype(np.float32, copy=False).reshape(-1)
        else:
            primary_vec = self._text_encoder.encode(text).astype(np.float32, copy=False).reshape(-1)

        # 2. Query expansion fusion (if enabled)
        variations = query_expander.expand_query(text)
        if len(variations) <= 1 or not settings.QUERY_EXPANSION_ENABLED:
            vector = primary_vec
        else:
            w_orig = settings.QUERY_EXPANSION_ORIGINAL_WEIGHT
            w_exp = settings.QUERY_EXPANSION_EXPANDED_WEIGHT

            other_vecs = []
            for var in variations[1:]:
                v = self._text_encoder.encode(var).astype(np.float32, copy=False).reshape(-1)
                other_vecs.append(v)

            if other_vecs:
                avg_other = np.mean(other_vecs, axis=0)
                fused = (w_orig * primary_vec) + (w_exp * avg_other)
                norm = float(np.linalg.norm(fused))
                if norm > 0:
                    vector = (fused / norm).astype(np.float32, copy=False)
                else:
                    vector = primary_vec
            else:
                vector = primary_vec

        self._embedding_cache.set(text, vector)
        return vector.reshape(-1), False

    def warm_up(self) -> None:
        """Run deep warmup across CLIP encoder, FAISS memory pages, and multi-concept fusion."""
        if not settings.CLIP_WARMUP_ENABLED or self._text_encoder is None:
            return
        query = settings.CLIP_WARMUP_QUERY.strip() or "a person walking in a room"
        try:
            # 1. Warm up text encoder with single and batch encodes
            self._text_encoder.encode(query)
            if hasattr(self._text_encoder, "encode_batch"):
                self._text_encoder.encode_batch(["a person walking", "a car on the street", "yellow building"])
            
            # 2. Warm up FAISS index memory pages and distance compute kernels
            if self._store is not None and self._store.stats.vector_count > 0:
                dummy_vec = np.zeros(self._store.stats.dimension, dtype=np.float32)
                dummy_vec[0] = 1.0
                self._store.search(dummy_vec, top_k=min(5, self._store.stats.vector_count))

            # 3. Warm up Multi-Concept Decomposition and Dynamic Saliency
            from app.algorithms.concept_decomposition import (
                build_multiconcept_fused_vector,
            )
            build_multiconcept_fused_vector("a person riding motorcycle near market", self._text_encoder)

            logger.info("kis_engine deep warmup complete (CLIP, FAISS, ConceptDecomposition)")
        except (RetrievalUnavailableError, RuntimeError, OSError, Exception) as exc:
            logger.warning("kis_engine warmup failed: %s", exc)

    def resolve_keyframe_path(self, video_id: str, frame_id: int) -> Path | None:
        """Resolve the canonical image path for a given video_id and frame_id/pts."""
        if self._store is not None:
            try:
                return self._store.image_path_for_frame(video_id, frame_id)
            except Exception:
                pass
        return None

    def search(self, english_text: str, top_k: int = 20) -> list[dict]:
        return self.search_with_metrics(english_text, top_k)[0]

    def search_with_metrics(self, english_text: str, top_k: int = 20) -> tuple[list[dict], dict[str, float]]:
        if self._store is None:
            raise RetrievalUnavailableError(self._startup_error or "KIS is not initialized.")
        if not english_text.strip():
            raise ValueError("Query text cannot be blank.")
        
        # Guard against empty vector store
        if self._store.stats.vector_count <= 0:
            raise RetrievalUnavailableError("Vector store is empty; index not loaded.")

        top_k = min(top_k, self._store.stats.vector_count)

        embedding_started_at = time.perf_counter()
        query_vector, embedding_cache_hit = self._encode_with_cache(english_text)
        query_vector = query_vector.copy().reshape(-1)
        embedding_time_ms = round((time.perf_counter() - embedding_started_at) * 1000, 2)

        faiss_started_at = time.perf_counter()
        hits = self._store.search(query_vector, top_k)
        faiss_time_ms = round((time.perf_counter() - faiss_started_at) * 1000, 2)

        metadata_started_at = time.perf_counter()
        results: list[dict] = []
        for hit in hits:
            try:
                result = validated_kis_result(
                    self._store.metadata_for(hit.vector_id),
                    hit.raw_score,
                    static_dir=settings.STATIC_DIR,
                    backend_host=settings.BACKEND_HOST,
                    vector_id=hit.vector_id,
                )
            except DatasetValidationError as exc:
                # A corrupt individual mapping must not crash a valid search.
                logger.warning("skipping_invalid_result vector_id=%s error=%s", hit.vector_id, exc)
                continue
            # attach provenance sources if available on the hit
            sources = getattr(hit, "sources", ()) or ()
            if sources:
                result["sources"] = list(sources)
                result["source"] = "fused" if len(sources) > 1 else sources[0]
            else:
                result["sources"] = ["faiss"]
                result["source"] = "faiss"
            result["rank"] = len(results) + 1
            results.append(result)
        metadata_time_ms = round((time.perf_counter() - metadata_started_at) * 1000, 2)

        return results, {
            "embedding_time_ms": embedding_time_ms,
            "faiss_time_ms": faiss_time_ms,
            "metadata_time_ms": metadata_time_ms,
            # Keep both keys for backward compatibility:
            "embedding_cache_hit": bool(embedding_cache_hit),
            "embedding_cache_hits": float(embedding_cache_hit),
        }

    def search_batch_with_metrics(
        self,
        english_texts: list[str],
        top_k: int = 20,
    ) -> tuple[list[list[dict]], dict[str, float]]:
        """Batch-encode queries and run one FAISS search for TRAKE multi-event paths."""
        if self._store is None:
            raise RetrievalUnavailableError(self._startup_error or "KIS is not initialized.")
        if not english_texts:
            return [], {
                "embedding_time_ms": 0.0,
                "faiss_time_ms": 0.0,
                "metadata_time_ms": 0.0,
                "embedding_cache_hits": 0.0,
            }
        
        # Guard against empty vector store
        if self._store.stats.vector_count <= 0:
            raise RetrievalUnavailableError("Vector store is empty; index not loaded.")

        top_k = min(top_k, self._store.stats.vector_count)
        embedding_started_at = time.perf_counter()
        vectors: list[np.ndarray] = []
        cache_hits = 0
        for text in english_texts:
            if not text.strip():
                raise ValueError("Query text cannot be blank.")
            vector, cache_hit = self._encode_with_cache(text)
            vectors.append(vector.copy().reshape(-1))
            cache_hits += int(cache_hit)
        query_matrix = np.vstack(vectors).astype(np.float32)
        embedding_time_ms = round((time.perf_counter() - embedding_started_at) * 1000, 2)

        faiss_started_at = time.perf_counter()
        hit_batches = self._store.search_batch(query_matrix, top_k)
        faiss_time_ms = round((time.perf_counter() - faiss_started_at) * 1000, 2)

        metadata_started_at = time.perf_counter()
        all_results: list[list[dict]] = []
        for hits in hit_batches:
            results: list[dict] = []
            for hit in hits:
                try:
                    result = validated_kis_result(
                        self._store.metadata_for(hit.vector_id),
                        hit.raw_score,
                        static_dir=settings.STATIC_DIR,
                        backend_host=settings.BACKEND_HOST,
                        vector_id=hit.vector_id,
                    )
                except DatasetValidationError as exc:
                    logger.warning(
                        "skipping_invalid_result vector_id=%s error=%s",
                        hit.vector_id,
                        exc,
                    )
                    continue
                # attach provenance sources if available on the hit
                sources = getattr(hit, "sources", ()) or ()
                if sources:
                    result["sources"] = list(sources)
                    result["source"] = "fused" if len(sources) > 1 else sources[0]
                else:
                    result["sources"] = ["faiss"]
                    result["source"] = "faiss"
                result["rank"] = len(results) + 1
                results.append(result)
            all_results.append(results)
        metadata_time_ms = round((time.perf_counter() - metadata_started_at) * 1000, 2)

        return all_results, {
            "embedding_time_ms": embedding_time_ms,
            "faiss_time_ms": faiss_time_ms,
            "metadata_time_ms": metadata_time_ms,
            # Batch returns aggregate hits (float) and a boolean flag if any cache hit occurred
            "embedding_cache_hits": float(cache_hits),
            "embedding_cache_hit": bool(cache_hits),
        }


kis_engine = KISEngine()
