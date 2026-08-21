import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv()


def _as_bool(value: str, *, default: bool) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _validate_url(value: str, field_name: str) -> str:
    """Validate that a string is a properly formatted URL if non-empty."""
    if not value.strip():
        return value
    try:
        result = urlparse(value)
        if not all([result.scheme, result.netloc]):
            raise ValueError(f"Invalid URL format for {field_name}: {value}")
        return value
    except Exception as exc:
        raise ValueError(f"Invalid URL format for {field_name}: {value}") from exc


def _validate_positive_float(value: float, field_name: str) -> float:
    """Validate that a float is positive."""
    if value <= 0:
        raise ValueError(f"{field_name} must be positive, got {value}")
    return value


def _validate_positive_int(value: int, field_name: str) -> int:
    """Validate that an int is positive."""
    if value <= 0:
        raise ValueError(f"{field_name} must be positive, got {value}")
    return value


def _validate_non_negative_int(value: int, field_name: str) -> int:
    """Validate that an int is non-negative (>= 0)."""
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative, got {value}")
    return value


def _validate_range(value: float, field_name: str, min_val: float, max_val: float) -> float:
    """Validate that a numeric value is within a specific range."""
    if not min_val <= value <= max_val:
        raise ValueError(f"{field_name} must be between {min_val} and {max_val}, got {value}")
    return value


@dataclass(frozen=True)
class Settings:
    """Typed application configuration, populated only from environment values."""

    PROJECT_NAME: str = os.getenv("PROJECT_NAME", "AIC 2026 Backend Engine")
    
    # Base directory for all paths - use current working directory for portability
    BASE_DIR: Path = Path(os.getenv("BASE_DIR", str(Path.cwd())))
    
    # All paths are relative to BASE_DIR for portability
    STATIC_DIR: Path = BASE_DIR / Path(os.getenv("STATIC_DIR", "static"))
    DATA_DIR: Path = BASE_DIR / Path(os.getenv("DATA_DIR", "data"))
    FEATURE_ROOT: Path = BASE_DIR / Path(os.getenv("FEATURE_ROOT", "data/features"))
    MAP_ROOT: Path = BASE_DIR / Path(os.getenv("MAP_ROOT", "data/map_keyframes/map-keyframes-aic25-b1/map-keyframes"))
    KEYFRAMES_DIR: Path = BASE_DIR / Path(os.getenv("KEYFRAMES_DIR", "static/keyframes"))
    VIDEOS_DIR: Path = BASE_DIR / Path(os.getenv("VIDEOS_DIR", "static/videos"))
    ZIP_INBOX_DIR: Path = BASE_DIR / Path(os.getenv("ZIP_INBOX_DIR", "data/inbox"))
    ZIP_INGEST_ENABLED: bool = _as_bool(
        os.getenv("ZIP_INGEST_ENABLED", "true"), default=True
    )
    OBJECT_ROOT: Path = BASE_DIR / Path(os.getenv("OBJECT_ROOT", "data/objects"))
    MEDIA_INFO_ROOT: Path = BASE_DIR / Path(os.getenv("MEDIA_INFO_ROOT", "data/media_info"))
    KIS_OBJECT_RERANK_ENABLED: bool = _as_bool(
        os.getenv("KIS_OBJECT_RERANK_ENABLED", "true"), default=True
    )
    KIS_OBJECT_RERANK_WEIGHT: float = _validate_range(
        float(os.getenv("KIS_OBJECT_RERANK_WEIGHT", "0.10")), "KIS_OBJECT_RERANK_WEIGHT", 0.0, 1.0
    )
    KIS_MEDIA_INFO_ENRICH_ENABLED: bool = _as_bool(
        os.getenv("KIS_MEDIA_INFO_ENRICH_ENABLED", "true"), default=True
    )
    KIS_MEDIA_INFO_RERANK_ENABLED: bool = _as_bool(
        os.getenv("KIS_MEDIA_INFO_RERANK_ENABLED", "true"), default=True
    )
    KIS_MEDIA_INFO_RERANK_WEIGHT: float = _validate_range(
        float(os.getenv("KIS_MEDIA_INFO_RERANK_WEIGHT", "0.10")), "KIS_MEDIA_INFO_RERANK_WEIGHT", 0.0, 1.0
    )
    HYBRID_METADATA_RERANK_ENABLED: bool = _as_bool(
        os.getenv("HYBRID_METADATA_RERANK_ENABLED", "true"), default=True
    )
    HYBRID_METADATA_RERANK_WEIGHT: float = _validate_range(
        float(os.getenv("HYBRID_METADATA_RERANK_WEIGHT", "0.12")),
        "HYBRID_METADATA_RERANK_WEIGHT",
        0.0,
        1.0,
    )
    # Temporal context smoothing
    TEMPORAL_SMOOTHING_ENABLED: bool = _as_bool(
        os.getenv("TEMPORAL_SMOOTHING_ENABLED", "true"), default=True
    )
    TEMPORAL_SMOOTHING_WINDOW_SECONDS: float = _validate_positive_float(
        float(os.getenv("TEMPORAL_SMOOTHING_WINDOW_SECONDS", "6.0")), "TEMPORAL_SMOOTHING_WINDOW_SECONDS"
    )
    TEMPORAL_SMOOTHING_SIGMA: float = _validate_positive_float(
        float(os.getenv("TEMPORAL_SMOOTHING_SIGMA", "3.0")), "TEMPORAL_SMOOTHING_SIGMA"
    )
    TEMPORAL_SMOOTHING_WEIGHT: float = _validate_range(
        float(os.getenv("TEMPORAL_SMOOTHING_WEIGHT", "0.15")), "TEMPORAL_SMOOTHING_WEIGHT", 0.0, 1.0
    )

    # KIS Candidate Pool Depth
    KIS_CANDIDATE_POOL_SIZE: int = _validate_positive_int(
        int(os.getenv("KIS_CANDIDATE_POOL_SIZE", "1000")), "KIS_CANDIDATE_POOL_SIZE"
    )

    # Regional Crop-Level CLIP Alignment
    KIS_CROP_ALIGNMENT_ENABLED: bool = _as_bool(
        os.getenv("KIS_CROP_ALIGNMENT_ENABLED", "true"), default=True
    )
    KIS_CROP_ALIGNMENT_WEIGHT: float = _validate_range(
        float(os.getenv("KIS_CROP_ALIGNMENT_WEIGHT", "0.12")), "KIS_CROP_ALIGNMENT_WEIGHT", 0.0, 1.0
    )
    KIS_CROP_ALIGNMENT_TOPK: int = _validate_non_negative_int(
        int(os.getenv("KIS_CROP_ALIGNMENT_TOPK", "5")), "KIS_CROP_ALIGNMENT_TOPK"
    )

    # Visual Pseudo-Relevance Feedback (Visual PRF / Rocchio)
    VISUAL_PRF_ENABLED: bool = _as_bool(os.getenv("VISUAL_PRF_ENABLED", "true"), default=True)
    VISUAL_PRF_TOPK: int = _validate_non_negative_int(int(os.getenv("VISUAL_PRF_TOPK", "3")), "VISUAL_PRF_TOPK")
    VISUAL_PRF_WEIGHT: float = _validate_range(
        float(os.getenv("VISUAL_PRF_WEIGHT", "0.20")), "VISUAL_PRF_WEIGHT", 0.0, 1.0
    )
    VISUAL_PRF_BLEND_ALPHA: float = _validate_range(
        float(os.getenv("VISUAL_PRF_BLEND_ALPHA", "0.30")), "VISUAL_PRF_BLEND_ALPHA", 0.0, 1.0
    )

    # Temporal Shot Consensus Graph Filtering
    TEMPORAL_CONSENSUS_ENABLED: bool = _as_bool(os.getenv("TEMPORAL_CONSENSUS_ENABLED", "true"), default=True)
    TEMPORAL_CONSENSUS_WINDOW_SECONDS: float = _validate_positive_float(
        float(os.getenv("TEMPORAL_CONSENSUS_WINDOW_SECONDS", "15.0")), "TEMPORAL_CONSENSUS_WINDOW_SECONDS"
    )
    TEMPORAL_CONSENSUS_BOOST_WEIGHT: float = _validate_range(
        float(os.getenv("TEMPORAL_CONSENSUS_BOOST_WEIGHT", "0.15")), "TEMPORAL_CONSENSUS_BOOST_WEIGHT", 0.0, 1.0
    )
    TEMPORAL_CONSENSUS_ISOLATED_PENALTY: float = _validate_range(
        float(os.getenv("TEMPORAL_CONSENSUS_ISOLATED_PENALTY", "0.04")), "TEMPORAL_CONSENSUS_ISOLATED_PENALTY", 0.0, 1.0
    )

    # Multi-Concept Semantic Decomposition & Orthogonal Fusion (P1)
    MULTI_CONCEPT_DECOMPOSITION_ENABLED: bool = _as_bool(
        os.getenv("MULTI_CONCEPT_DECOMPOSITION_ENABLED", "true"), default=True
    )
    MULTI_CONCEPT_WEIGHT_GLOBAL: float = _validate_range(
        float(os.getenv("MULTI_CONCEPT_WEIGHT_GLOBAL", "0.45")), "MULTI_CONCEPT_WEIGHT_GLOBAL", 0.0, 1.0
    )
    MULTI_CONCEPT_WEIGHT_ENTITY: float = _validate_range(
        float(os.getenv("MULTI_CONCEPT_WEIGHT_ENTITY", "0.20")), "MULTI_CONCEPT_WEIGHT_ENTITY", 0.0, 1.0
    )
    MULTI_CONCEPT_WEIGHT_ATTRIBUTE: float = _validate_range(
        float(os.getenv("MULTI_CONCEPT_WEIGHT_ATTRIBUTE", "0.15")), "MULTI_CONCEPT_WEIGHT_ATTRIBUTE", 0.0, 1.0
    )
    MULTI_CONCEPT_WEIGHT_ACTION: float = _validate_range(
        float(os.getenv("MULTI_CONCEPT_WEIGHT_ACTION", "0.10")), "MULTI_CONCEPT_WEIGHT_ACTION", 0.0, 1.0
    )
    MULTI_CONCEPT_WEIGHT_SCENE: float = _validate_range(
        float(os.getenv("MULTI_CONCEPT_WEIGHT_SCENE", "0.10")), "MULTI_CONCEPT_WEIGHT_SCENE", 0.0, 1.0
    )

    # Intra-video diversification & deduplication
    DIVERSIFICATION_ENABLED: bool = _as_bool(
        os.getenv("DIVERSIFICATION_ENABLED", "true"), default=True
    )
    DIVERSIFICATION_MIN_GAP_SECONDS: float = _validate_positive_float(
        float(os.getenv("DIVERSIFICATION_MIN_GAP_SECONDS", "3.5")), "DIVERSIFICATION_MIN_GAP_SECONDS"
    )
    DIVERSIFICATION_MAX_PER_VIDEO: int = _validate_positive_int(
        int(os.getenv("DIVERSIFICATION_MAX_PER_VIDEO", "3")), "DIVERSIFICATION_MAX_PER_VIDEO"
    )
    DIVERSIFICATION_MODE: str = os.getenv("DIVERSIFICATION_MODE", "soft_penalty")
    DIVERSIFICATION_PENALTY_WEIGHT: float = _validate_range(
        float(os.getenv("DIVERSIFICATION_PENALTY_WEIGHT", "0.08")), "DIVERSIFICATION_PENALTY_WEIGHT", 0.0, 1.0
    )

    # Cross-encoder rescoring (lightweight proxy using image embeddings)
    CROSS_ENCODER_ENABLED: bool = _as_bool(os.getenv("CROSS_ENCODER_ENABLED", "false"), default=False)
    CROSS_ENCODER_TOP_K: int = _validate_positive_int(int(os.getenv("CROSS_ENCODER_TOP_K", "20")), "CROSS_ENCODER_TOP_K")
    CROSS_ENCODER_WEIGHT: float = _validate_range(float(os.getenv("CROSS_ENCODER_WEIGHT", "0.7")), "CROSS_ENCODER_WEIGHT", 0.0, 1.0)
    
    # TRAKE temporal alignment settings
    TRAKE_MAX_GAP_SECONDS: float = _validate_range(float(os.getenv("TRAKE_MAX_GAP_SECONDS", "300.0")), "TRAKE_MAX_GAP_SECONDS", 0.0, 3600.0)
    TRAKE_TARGET_GAP_SECONDS: float = _validate_range(float(os.getenv("TRAKE_TARGET_GAP_SECONDS", "15.0")), "TRAKE_TARGET_GAP_SECONDS", 0.0, 3600.0)
    TRAKE_GAP_SIGMA_SECONDS: float = _validate_range(float(os.getenv("TRAKE_GAP_SIGMA_SECONDS", "25.0")), "TRAKE_GAP_SIGMA_SECONDS", 0.1, 3600.0)

    SUBMISSION_DIR: Path = BASE_DIR / Path(os.getenv("SUBMISSION_DIR", "submission"))
    FAISS_INDEX_PATH: Path = BASE_DIR / Path(os.getenv("FAISS_INDEX_PATH", "data/faiss_index.bin"))
    METADATA_PATH: Path = BASE_DIR / Path(os.getenv("METADATA_PATH", "data/metadata.json"))
    VECTOR_BACKEND: str = os.getenv("VECTOR_BACKEND", "faiss")
    # When False (default), missing image files produce a warning but do NOT drop the result.
    # Set to True only in strict dev environments where all keyframe images are guaranteed present.
    STRICT_IMAGE_VALIDATION: bool = _as_bool(
        os.getenv("STRICT_IMAGE_VALIDATION", "false"), default=False
    )
    MILVUS_URI: str = _validate_url(os.getenv("MILVUS_URI", "tcp://milvus:19530"), "MILVUS_URI")
    MILVUS_COLLECTION: str = os.getenv("MILVUS_COLLECTION", "aic_keyframes")
    MILVUS_TIMEOUT_SECONDS: float = _validate_positive_float(float(os.getenv("MILVUS_TIMEOUT_SECONDS", "5")), "MILVUS_TIMEOUT_SECONDS")
    QDRANT_URL: str = _validate_url(os.getenv("QDRANT_URL", "http://localhost:6333"), "QDRANT_URL")
    QDRANT_API_KEY: str | None = os.getenv("QDRANT_API_KEY")
    QDRANT_COLLECTION: str = os.getenv("QDRANT_COLLECTION", "aic_keyframes")
    QDRANT_TIMEOUT_SECONDS: float = _validate_positive_float(float(os.getenv("QDRANT_TIMEOUT_SECONDS", "5")), "QDRANT_TIMEOUT_SECONDS")
    HYBRID_RRF_K: int = _validate_positive_int(int(os.getenv("HYBRID_RRF_K", "60")), "HYBRID_RRF_K")
    AI_PROVIDER_MODE: str = os.getenv("AI_PROVIDER_MODE", "mock")
    TEXT_ENCODER_PROVIDER: str = os.getenv("TEXT_ENCODER_PROVIDER", "mock")
    TEXT_ENCODER_FALLBACK_TO_MOCK: bool = _as_bool(
        os.getenv("TEXT_ENCODER_FALLBACK_TO_MOCK", "true"), default=True
    )
    CLIP_MODEL_NAME: str = os.getenv(
        "CLIP_MODEL_NAME", "sentence-transformers/clip-ViT-B-32"
    )
    TEXT_ENCODER_ENSEMBLE_ENABLED: bool = _as_bool(
        os.getenv("TEXT_ENCODER_ENSEMBLE_ENABLED", "false"), default=False
    )
    ENSEMBLE_MODEL_NAME: str = os.getenv(
        "ENSEMBLE_MODEL_NAME", "sentence-transformers/clip-ViT-B-32-multilingual-v1"
    )
    ENSEMBLE_PRIMARY_WEIGHT: float = _validate_range(
        float(os.getenv("ENSEMBLE_PRIMARY_WEIGHT", "0.5")), "ENSEMBLE_PRIMARY_WEIGHT", 0.0, 1.0
    )
    ENSEMBLE_SECONDARY_WEIGHT: float = _validate_range(
        float(os.getenv("ENSEMBLE_SECONDARY_WEIGHT", "0.5")), "ENSEMBLE_SECONDARY_WEIGHT", 0.0, 1.0
    )
    MOCK_EMBEDDING_DIM: int = _validate_positive_int(int(os.getenv("MOCK_EMBEDDING_DIM", "512")), "MOCK_EMBEDDING_DIM")
    TRANSLATION_ENABLED: bool = _as_bool(
        os.getenv("TRANSLATION_ENABLED", "true"), default=True
    )
    TRANSLATION_PROVIDER: str = os.getenv("TRANSLATION_PROVIDER", "google_gtx")
    TRANSLATION_SOURCE_LANGUAGE: str = os.getenv("TRANSLATION_SOURCE_LANGUAGE", "vi")
    TRANSLATION_TARGET_LANGUAGE: str = os.getenv("TRANSLATION_TARGET_LANGUAGE", "en")
    GOOGLE_TRANSLATION_API_BASE: str = _validate_url(os.getenv("GOOGLE_TRANSLATION_API_BASE", "https://translate.googleapis.com"), "GOOGLE_TRANSLATION_API_BASE")
    BACKEND_HOST: str = _validate_url(os.getenv("BACKEND_HOST", "http://0.0.0.0:8000"), "BACKEND_HOST")
    CORS_ORIGINS: str = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000")
    SEARCH_API_ENDPOINT: str = os.getenv("SEARCH_API_ENDPOINT", "/api/v1/search")
    STATIC_PATH: str = os.getenv("STATIC_PATH", "/static/keyframes")
    TOP_K_DEFAULT: int = _validate_positive_int(int(os.getenv("TOP_K_DEFAULT", "20")), "TOP_K_DEFAULT")
    MAX_QUERY_LENGTH: int = _validate_positive_int(int(os.getenv("MAX_QUERY_LENGTH", "1000")), "MAX_QUERY_LENGTH")
    MAX_TOP_K: int = _validate_positive_int(int(os.getenv("MAX_TOP_K", "100")), "MAX_TOP_K")
    KIS_QUERY_TEMPLATES: str = os.getenv(
        "KIS_QUERY_TEMPLATES",
        "{query}|a photo of {query}|an image of {query}|a video frame of {query}",
    )
    QUERY_EXPANSION_ENABLED: bool = _as_bool(
        os.getenv("QUERY_EXPANSION_ENABLED", "true"), default=True
    )
    QUERY_EXPANSION_MODE: str = os.getenv("QUERY_EXPANSION_MODE", "hybrid")
    QUERY_EXPANSION_NUM_VARIATIONS: int = _validate_positive_int(
        int(os.getenv("QUERY_EXPANSION_NUM_VARIATIONS", "3")), "QUERY_EXPANSION_NUM_VARIATIONS"
    )
    QUERY_EXPANSION_ORIGINAL_WEIGHT: float = _validate_range(
        float(os.getenv("QUERY_EXPANSION_ORIGINAL_WEIGHT", "0.6")), "QUERY_EXPANSION_ORIGINAL_WEIGHT", 0.0, 1.0
    )
    QUERY_EXPANSION_EXPANDED_WEIGHT: float = _validate_range(
        float(os.getenv("QUERY_EXPANSION_EXPANDED_WEIGHT", "0.4")), "QUERY_EXPANSION_EXPANDED_WEIGHT", 0.0, 1.0
    )
    QUERY_EXPANSION_CACHE_TTL_SECONDS: int = _validate_positive_int(
        int(os.getenv("QUERY_EXPANSION_CACHE_TTL_SECONDS", "86400")), "QUERY_EXPANSION_CACHE_TTL_SECONDS"
    )
    TRANSLATION_TIMEOUT_SECONDS: float = _validate_positive_float(
        float(os.getenv("TRANSLATION_TIMEOUT_SECONDS", "3")), "TRANSLATION_TIMEOUT_SECONDS"
    )
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_API_BASE: str = _validate_url(os.getenv("GEMINI_API_BASE", "https://generativelanguage.googleapis.com"), "GEMINI_API_BASE")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_API_BASE: str = _validate_url(os.getenv("OPENAI_API_BASE", "https://api.openai.com"), "OPENAI_API_BASE")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-flash-latest")
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    ANTHROPIC_API_BASE: str = _validate_url(os.getenv("ANTHROPIC_API_BASE", "https://api.anthropic.com"), "ANTHROPIC_API_BASE")
    VQA_PROVIDER: str = os.getenv("VQA_PROVIDER", "gemini")
    VQA_TIMEOUT_SECONDS: float = _validate_positive_float(float(os.getenv("VQA_TIMEOUT_SECONDS", "15")), "VQA_TIMEOUT_SECONDS")
    VQA_MAX_CONCURRENCY: int = _validate_positive_int(int(os.getenv("VQA_MAX_CONCURRENCY", "8")), "VQA_MAX_CONCURRENCY")
    VQA_COUNTING_STRATEGY: str = os.getenv("VQA_COUNTING_STRATEGY", "vlm_primary")
    SPATIAL_VQA_ATTENTION_ENABLED: bool = _as_bool(
        os.getenv("SPATIAL_VQA_ATTENTION_ENABLED", "true"), default=True
    )
    TEMPORAL_VQA_CONTEXT_ENABLED: bool = _as_bool(
        os.getenv("TEMPORAL_VQA_CONTEXT_ENABLED", "true"), default=True
    )
    OPENAI_VQA_MODEL: str = os.getenv(
        "OPENAI_VQA_MODEL",
        os.getenv("OPENAI_TRANSLATION_MODEL", "gpt-4o-mini"),
    )
    CLAUDE_VQA_MODEL: str = os.getenv("CLAUDE_VQA_MODEL", "claude-3-5-haiku-latest")
    QWEN_API_KEY: str = os.getenv("QWEN_API_KEY", "")
    QWEN_VQA_MODEL: str = os.getenv("QWEN_VQA_MODEL", "qwen-vl-max")
    QWEN_API_BASE: str = _validate_url(
        os.getenv("QWEN_API_BASE", "https://dashscope.aliyuncs.com/compatible-mode/v1"), "QWEN_API_BASE"
    )
    GEMINI_TRANSLATION_MODEL: str = os.getenv(
        "GEMINI_TRANSLATION_MODEL", "gemini-flash-latest"
    )
    OPENAI_TRANSLATION_MODEL: str = os.getenv("OPENAI_TRANSLATION_MODEL", "gpt-4o-mini")
    KIS_SELFCHECK_SAMPLE_SIZE: int = _validate_positive_int(int(os.getenv("KIS_SELFCHECK_SAMPLE_SIZE", "5")), "KIS_SELFCHECK_SAMPLE_SIZE")
    KIS_SELFCHECK_MIN_IMAGE_COSINE: float = _validate_range(
        float(os.getenv("KIS_SELFCHECK_MIN_IMAGE_COSINE", "0.99")), "KIS_SELFCHECK_MIN_IMAGE_COSINE", 0.0, 1.0
    )
    CACHE_BACKEND: str = os.getenv("CACHE_BACKEND", "memory")
    REDIS_URL: str = os.getenv("REDIS_URL", "")
    CACHE_MAX_ENTRIES: int = _validate_positive_int(int(os.getenv("CACHE_MAX_ENTRIES", "2048")), "CACHE_MAX_ENTRIES")
    EMBEDDING_CACHE_TTL_SECONDS: int = int(os.getenv("EMBEDDING_CACHE_TTL_SECONDS", "0"))
    TRANSLATION_CACHE_TTL_SECONDS: int = int(os.getenv("TRANSLATION_CACHE_TTL_SECONDS", "0"))
    VLM_CACHE_TTL_SECONDS: int = int(os.getenv("VLM_CACHE_TTL_SECONDS", "0"))
    LATENCY_SLA_MS: float = _validate_positive_float(float(os.getenv("LATENCY_SLA_MS", "1000")), "LATENCY_SLA_MS")
    CLIP_WARMUP_ENABLED: bool = _as_bool(os.getenv("CLIP_WARMUP_ENABLED", "true"), default=True)
    CLIP_WARMUP_QUERY: str = os.getenv("CLIP_WARMUP_QUERY", "a person walking in a room")
    LATENCY_BENCHMARK_WARMUP: int = _validate_positive_int(int(os.getenv("LATENCY_BENCHMARK_WARMUP", "2")), "LATENCY_BENCHMARK_WARMUP")
    LATENCY_BENCHMARK_REPEATS: int = _validate_positive_int(int(os.getenv("LATENCY_BENCHMARK_REPEATS", "10")), "LATENCY_BENCHMARK_REPEATS")
    MOCK_COMPETITION_BUDGET_HOURS: float = _validate_positive_float(float(os.getenv("MOCK_COMPETITION_BUDGET_HOURS", "3")), "MOCK_COMPETITION_BUDGET_HOURS")
    MOCK_COMPETITION_SAMPLE_FRACTION: float = _validate_range(
        float(os.getenv("MOCK_COMPETITION_SAMPLE_FRACTION", "0.5")), "MOCK_COMPETITION_SAMPLE_FRACTION", 0.0, 1.0
    )

    def __post_init__(self) -> None:
        """Validate critical configuration values that don't have inline validation."""
        # Validate REDIS_URL only if it's not empty
        if self.REDIS_URL:
            _validate_url(self.REDIS_URL, "REDIS_URL")
        
        # Validate directory paths exist or can be created
        # For contest use, we should be more flexible - only validate critical directories
        self._validate_directory("STATIC_DIR", self.STATIC_DIR, create=True, required=False)
        self._validate_directory("DATA_DIR", self.DATA_DIR, create=True, required=False)
        self._validate_directory("FEATURE_ROOT", self.FEATURE_ROOT, create=False, required=False)
        self._validate_directory("MAP_ROOT", self.MAP_ROOT, create=False, required=False)
        self._validate_directory("KEYFRAMES_DIR", self.KEYFRAMES_DIR, create=False, required=False)
        self._validate_directory("ZIP_INBOX_DIR", self.ZIP_INBOX_DIR, create=True, required=False)
        self._validate_directory("SUBMISSION_DIR", self.SUBMISSION_DIR, create=True, required=False)
        
        # Validate vector backend configuration - be more flexible
        valid_vector_backends = {
            "faiss", "milvus", "hybrid", "qdrant",  # Standard names
            "faiss_only", "milvus_only",              # Alternative names
        }
        if self.VECTOR_BACKEND.lower() not in [v.lower() for v in valid_vector_backends]:
            raise ValueError(
                f"VECTOR_BACKEND must be one of {valid_vector_backends}, got '{self.VECTOR_BACKEND}'"
            )
        
        # Validate Milvus configuration if using hybrid or milvus backend
        if self.VECTOR_BACKEND in {"milvus", "hybrid"}:
            if not self.MILVUS_URI:
                raise ValueError("MILVUS_URI is required when VECTOR_BACKEND is 'milvus' or 'hybrid'")
            _validate_url(self.MILVUS_URI, "MILVUS_URI")
        
        # Validate AI provider mode - be more flexible
        valid_ai_modes = {"real", "mock", "production", "development"}
        if self.AI_PROVIDER_MODE.lower() not in [v.lower() for v in valid_ai_modes]:
            raise ValueError(
                f"AI_PROVIDER_MODE must be one of {valid_ai_modes}, got '{self.AI_PROVIDER_MODE}'"
            )
        
        # Validate cache backend - be more flexible
        valid_cache_backends = {"memory", "redis", "none", "disabled"}
        if self.CACHE_BACKEND.lower() not in [v.lower() for v in valid_cache_backends]:
            raise ValueError(
                f"CACHE_BACKEND must be one of {valid_cache_backends}, got '{self.CACHE_BACKEND}'"
            )
        
        # Validate Redis configuration if using Redis cache
        if self.CACHE_BACKEND == "redis" and not self.REDIS_URL:
            raise ValueError("REDIS_URL is required when CACHE_BACKEND is 'redis'")
        
        # Validate text encoder provider - allow common providers
        # Include both the internal codes and common external library names
        valid_text_encoders = {
            "clip", "mock",  # Internal codes
            "sentence_transformers", "sentence-transformers",  # Common library names
            "huggingface", "hf",  # Alternative names
        }
        if self.TEXT_ENCODER_PROVIDER.lower() not in [v.lower() for v in valid_text_encoders]:
            raise ValueError(
                f"TEXT_ENCODER_PROVIDER must be one of {valid_text_encoders}, got '{self.TEXT_ENCODER_PROVIDER}'"
            )
        
        # Validate VQA provider - be more flexible with common names
        valid_vqa_providers = {
            "gemini", "openai", "anthropic", "qwen", "mock",  # Standard names
            "google", "gpt", "claude",  # Alternative names
        }
        if self.VQA_PROVIDER.lower() not in [v.lower() for v in valid_vqa_providers]:
            raise ValueError(
                f"VQA_PROVIDER must be one of {valid_vqa_providers}, got '{self.VQA_PROVIDER}'"
            )
        
        # Validate translation provider - be more flexible
        valid_translation_providers = {
            "google_gtx", "openai", "gemini", "mock",  # Standard names
            "google", "gpt", "noop",                   # Alternative names
        }
        if self.TRANSLATION_PROVIDER.lower() not in [v.lower() for v in valid_translation_providers]:
            raise ValueError(
                f"TRANSLATION_PROVIDER must be one of {valid_translation_providers}, got '{self.TRANSLATION_PROVIDER}'"
            )
        
        # Validate API keys for real mode - be strict in production
        if self.AI_PROVIDER_MODE.lower() in {"real", "production"}:
            # Raise errors for missing API keys in production mode
            if self.VQA_PROVIDER.lower() in {"gemini", "google"} and not self.GEMINI_API_KEY:
                raise ValueError("GEMINI_API_KEY is required when VQA_PROVIDER is Gemini in production mode.")
            
            if self.VQA_PROVIDER.lower() in {"openai", "gpt"} and not self.OPENAI_API_KEY:
                raise ValueError("OPENAI_API_KEY is required when VQA_PROVIDER is OpenAI in production mode.")
            
            if self.VQA_PROVIDER.lower() in {"anthropic", "claude"} and not self.ANTHROPIC_API_KEY:
                raise ValueError("ANTHROPIC_API_KEY is required when VQA_PROVIDER is Anthropic in production mode.")
            
            if self.VQA_PROVIDER.lower() == "qwen" and not self.QWEN_API_KEY:
                raise ValueError("QWEN_API_KEY is required when VQA_PROVIDER is Qwen in production mode.")
        else:
            # In development/mock mode, just warn about missing keys
            import warnings
            if self.VQA_PROVIDER.lower() in {"gemini", "google"} and not self.GEMINI_API_KEY:
                warnings.warn("GEMINI_API_KEY is not configured. VQA with Gemini may not work.")
            if self.VQA_PROVIDER.lower() in {"openai", "gpt"} and not self.OPENAI_API_KEY:
                warnings.warn("OPENAI_API_KEY is not configured. VQA with OpenAI may not work.")
            if self.VQA_PROVIDER.lower() in {"anthropic", "claude"} and not self.ANTHROPIC_API_KEY:
                warnings.warn("ANTHROPIC_API_KEY is not configured. VQA with Anthropic may not work.")
            if self.VQA_PROVIDER.lower() == "qwen" and not self.QWEN_API_KEY:
                warnings.warn("QWEN_API_KEY is not configured. VQA with Qwen may not work.")
    
    def _validate_directory(self, name: str, path: Path, create: bool = False, required: bool = True) -> None:
        """Validate a directory path, optionally creating it.
        
        Args:
            name: Directory name for error messages
            path: Directory path to validate
            create: Whether to create the directory if it doesn't exist
            required: Whether the directory must exist (False = optional directory)
        """
        if not path.exists():
            if create:
                try:
                    path.mkdir(parents=True, exist_ok=True)
                except OSError as e:
                    if required:
                        raise ValueError(
                            f"Failed to create {name} at {path}: {e}"
                        ) from e
                    # For optional directories, just log warning
                    import warnings
                    warnings.warn(f"Optional directory {name} could not be created at {path}: {e}")
            else:
                if required:
                    raise ValueError(
                        f"{name} directory does not exist: {path}. "
                        f"Please create it or update your configuration."
                    )
                # For optional directories, just skip validation
                return
        elif not path.is_dir():
            if required:
                raise ValueError(
                    f"{name} path exists but is not a directory: {path}"
                )


settings = Settings()
