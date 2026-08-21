"""Small helpers for latency benchmarking and SLA checks."""

from __future__ import annotations

from collections.abc import Iterable


def percentile(values: Iterable[float], pct: float) -> float:
    """Return the p-th percentile (0–100) using linear interpolation."""
    samples = sorted(float(value) for value in values)
    if not samples:
        return 0.0
    if len(samples) == 1:
        return samples[0]

    rank = (pct / 100.0) * (len(samples) - 1)
    lower = int(rank)
    upper = min(lower + 1, len(samples) - 1)
    weight = rank - lower
    return round(samples[lower] * (1.0 - weight) + samples[upper] * weight, 2)


def summarize_latencies(values: Iterable[float]) -> dict[str, float]:
    samples = [float(value) for value in values]
    if not samples:
        return {
            "count": 0.0,
            "min_ms": 0.0,
            "max_ms": 0.0,
            "mean_ms": 0.0,
            "p50_ms": 0.0,
            "p95_ms": 0.0,
            "p99_ms": 0.0,
        }

    return {
        "count": float(len(samples)),
        "min_ms": round(min(samples), 2),
        "max_ms": round(max(samples), 2),
        "mean_ms": round(sum(samples) / len(samples), 2),
        "p50_ms": percentile(samples, 50),
        "p95_ms": percentile(samples, 95),
        "p99_ms": percentile(samples, 99),
    }
