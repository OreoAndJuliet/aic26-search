"""Runtime checks for KIS vector parsing and CLIP alignment."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from app.core.config import settings
from app.core.exceptions import DatasetValidationError, EmbeddingDimensionMismatchError
from app.providers.text_encoder import TextEncoder

if TYPE_CHECKING:
    from app.services.kis_engine import KISEngine


@dataclass(frozen=True)
class SelfCheckItem:
    name: str
    passed: bool
    detail: str
    data: dict[str, Any]


@dataclass(frozen=True)
class SelfCheckReport:
    status: str
    checks: tuple[SelfCheckItem, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "checks": [
                {
                    "name": item.name,
                    "passed": item.passed,
                    "detail": item.detail,
                    **item.data,
                }
                for item in self.checks
            ],
        }


def sample_vector_ids(sample_size: int, vector_count: int) -> list[int]:
    if vector_count <= 0:
        return []
    if sample_size >= vector_count:
        return list(range(vector_count))
    if sample_size <= 1:
        return [0]

    step = (vector_count - 1) / (sample_size - 1)
    return [round(index * step) for index in range(sample_size)]


def _unit_vector_checks(name: str, vector: np.ndarray, expected_dim: int) -> SelfCheckItem:
    if vector.ndim != 1:
        return SelfCheckItem(
            name=name,
            passed=False,
            detail="Embedding must be one-dimensional.",
            data={"shape": list(vector.shape)},
        )

    norm = float(np.linalg.norm(vector))
    passed = vector.shape[0] == expected_dim and math.isfinite(norm) and math.isclose(
        norm, 1.0, rel_tol=1e-4, abs_tol=1e-4
    )
    detail = (
        f"dimension={vector.shape[0]}, norm={norm:.6f}"
        if passed
        else (
            f"Expected dimension {expected_dim} and unit norm, got "
            f"dimension={vector.shape[0]}, norm={norm:.6f}"
        )
    )
    return SelfCheckItem(
        name=name,
        passed=passed,
        detail=detail,
        data={"dimension": int(vector.shape[0]), "norm": norm},
    )


def check_query_embedding(engine: KISEngine) -> SelfCheckItem:
    stats = engine.stats
    query_vector = engine.encode_query_vector("kis selfcheck probe")
    return _unit_vector_checks("query_embedding", query_vector, stats.dimension)


def _supports_image_encoding(encoder: TextEncoder) -> bool:
    return type(encoder).encode_image is not TextEncoder.encode_image


def check_image_alignment(
    engine: KISEngine,
    *,
    sample_size: int,
    min_cosine: float,
) -> SelfCheckItem:
    encoder = engine.text_encoder
    if not _supports_image_encoding(encoder):
        return SelfCheckItem(
            name="image_alignment",
            passed=True,
            detail="Skipped because the configured text encoder does not support image encoding.",
            data={"skipped": True},
        )

    store = engine.store
    vector_ids = sample_vector_ids(sample_size, store.stats.vector_count)
    samples: list[dict[str, Any]] = []
    min_observed = 1.0

    for vector_id in vector_ids:
        metadata = store.metadata_for(vector_id)
        image_path = Path(str(metadata["image_path"]))
        if not image_path.is_file():
            raise DatasetValidationError(
                f"Self-check keyframe is missing for vector_id={vector_id}: {image_path}"
            )

        stored_vector = store.reconstruct(vector_id)
        live_vector = encoder.encode_image(image_path).reshape(-1)
        cosine = float(np.dot(stored_vector, live_vector))
        min_observed = min(min_observed, cosine)
        samples.append(
            {
                "vector_id": vector_id,
                "video_id": metadata["video_id"],
                "keyframe_id": metadata["keyframe_id"],
                "cosine": round(cosine, 6),
            }
        )

    passed = min_observed >= min_cosine
    detail = (
        f"min_cosine={min_observed:.6f} across {len(samples)} sampled keyframes"
        if passed
        else (
            f"Minimum cosine {min_observed:.6f} is below threshold {min_cosine:.6f} "
            f"for sampled keyframes."
        )
    )
    return SelfCheckItem(
        name="image_alignment",
        passed=passed,
        detail=detail,
        data={
            "sample_size": len(samples),
            "min_cosine": min_observed,
            "threshold": min_cosine,
            "samples": samples,
        },
    )


def run_kis_selfcheck(
    engine: KISEngine,
    *,
    sample_size: int | None = None,
    min_image_cosine: float | None = None,
    include_alignment: bool = True,
) -> SelfCheckReport:
    """Validate query-vector parsing and optional CLIP image alignment."""
    resolved_sample_size = (
        settings.KIS_SELFCHECK_SAMPLE_SIZE if sample_size is None else sample_size
    )
    resolved_min_cosine = (
        settings.KIS_SELFCHECK_MIN_IMAGE_COSINE
        if min_image_cosine is None
        else min_image_cosine
    )

    checks: list[SelfCheckItem] = [check_query_embedding(engine)]
    if include_alignment:
        checks.append(
            check_image_alignment(
                engine,
                sample_size=resolved_sample_size,
                min_cosine=resolved_min_cosine,
            )
        )

    status = "ok" if all(item.passed for item in checks) else "failed"
    return SelfCheckReport(status=status, checks=tuple(checks))


def assert_selfcheck_passes(report: SelfCheckReport) -> None:
    if report.status == "ok":
        return
    failed_details = "; ".join(
        f"{item.name}: {item.detail}" for item in report.checks if not item.passed
    )
    if any(item.name == "query_embedding" and not item.passed for item in report.checks):
        raise EmbeddingDimensionMismatchError(failed_details)
    raise DatasetValidationError(failed_details)
