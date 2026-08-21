"""Benchmark KIS latency with cold/warm cache comparison."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import httpx

from app.core.config import settings
from app.services.kis_engine import kis_engine
from app.services.translator import translator
from app.utils.latency_stats import summarize_latencies

DEFAULT_QUERIES = (
    "a person walking in a room",
    "a car driving on the street",
    "một người đi bộ trong phòng",
    "xe hơi chạy trên đường",
)


def _run_inprocess_kis(
    queries: tuple[str, ...],
    *,
    top_k: int,
    warmup: int,
) -> dict[str, Any]:
    kis_engine.initialize()

    for _ in range(warmup):
        for query in queries:
            kis_engine.search_with_metrics(query, top_k)

    kis_engine._embedding_cache.clear()
    translator._translation_cache.clear()

    cold_total_ms: list[float] = []
    cold_embedding_ms: list[float] = []
    cold_cache_hits = 0
    for query in queries:
        started_at = time.perf_counter()
        _, metrics = kis_engine.search_with_metrics(query, top_k)
        cold_total_ms.append(round((time.perf_counter() - started_at) * 1000, 2))
        cold_embedding_ms.append(float(metrics["embedding_time_ms"]))
        cold_cache_hits += int(bool(metrics.get("embedding_cache_hit")))

    warm_total_ms: list[float] = []
    warm_embedding_ms: list[float] = []
    warm_cache_hits = 0
    warm_runs = max(settings.LATENCY_BENCHMARK_REPEATS, 1)
    for _ in range(warm_runs):
        for query in queries:
            started_at = time.perf_counter()
            _, metrics = kis_engine.search_with_metrics(query, top_k)
            warm_total_ms.append(round((time.perf_counter() - started_at) * 1000, 2))
            warm_embedding_ms.append(float(metrics["embedding_time_ms"]))
            warm_cache_hits += int(bool(metrics.get("embedding_cache_hit")))

    return {
        "mode": "inprocess",
        "provider": settings.TEXT_ENCODER_PROVIDER,
        "cache_backend": settings.CACHE_BACKEND,
        "top_k": top_k,
        "queries": list(queries),
        "cold": {
            "total_ms": summarize_latencies(cold_total_ms),
            "embedding_ms": summarize_latencies(cold_embedding_ms),
            "embedding_cache_hits": cold_cache_hits,
            "embedding_cache_misses": len(queries) - cold_cache_hits,
        },
        "warm": {
            "total_ms": summarize_latencies(warm_total_ms),
            "embedding_ms": summarize_latencies(warm_embedding_ms),
            "embedding_cache_hits": warm_cache_hits,
            "embedding_cache_misses": len(warm_total_ms) - warm_cache_hits,
        },
    }


def _run_http_kis(
    queries: tuple[str, ...],
    *,
    base_url: str,
    top_k: int,
    warmup: int,
) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/api/v1/search"
    payload_base = {"type": "KIS", "top_k": top_k}

    with httpx.Client(timeout=30.0) as client:
        for _ in range(warmup):
            for query in queries:
                client.post(url, json={**payload_base, "text": query})

        cold_total_ms: list[float] = []
        for query in queries:
            started_at = time.perf_counter()
            response = client.post(url, json={**payload_base, "text": query})
            response.raise_for_status()
            cold_total_ms.append(round((time.perf_counter() - started_at) * 1000, 2))

        warm_total_ms: list[float] = []
        warm_runs = max(settings.LATENCY_BENCHMARK_REPEATS, 1)
        for _ in range(warm_runs):
            for query in queries:
                started_at = time.perf_counter()
                response = client.post(url, json={**payload_base, "text": query})
                response.raise_for_status()
                payload = response.json()
                warm_total_ms.append(float(payload.get("total_time_ms", 0.0)))

    return {
        "mode": "http",
        "base_url": base_url,
        "top_k": top_k,
        "queries": list(queries),
        "cold": {"total_ms": summarize_latencies(cold_total_ms)},
        "warm": {"total_ms": summarize_latencies(warm_total_ms)},
    }


def _evaluate_sla(report: dict[str, Any], sla_ms: float) -> dict[str, Any]:
    warm = report.get("warm", {})
    total = warm.get("total_ms", {})
    p95_ms = float(total.get("p95_ms", 0.0))
    return {
        "sla_ms": sla_ms,
        "warm_p95_ms": p95_ms,
        "passed": p95_ms <= sla_ms,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Benchmark KIS search latency.")
    parser.add_argument(
        "--mode",
        choices=("inprocess", "http"),
        default="inprocess",
        help="Benchmark in-process KIS or live HTTP /api/v1/search.",
    )
    parser.add_argument(
        "--base-url",
        default=settings.BACKEND_HOST,
        help="Base URL for --mode http.",
    )
    parser.add_argument("--top-k", type=int, default=min(settings.TOP_K_DEFAULT, 20))
    parser.add_argument("--warmup", type=int, default=settings.LATENCY_BENCHMARK_WARMUP)
    parser.add_argument("--sla-ms", type=float, default=settings.LATENCY_SLA_MS)
    parser.add_argument(
        "--queries",
        nargs="*",
        default=list(DEFAULT_QUERIES),
        help="Queries to benchmark.",
    )
    args = parser.parse_args(argv)

    queries = tuple(query.strip() for query in args.queries if query.strip())
    if not queries:
        print("At least one query is required.", file=sys.stderr)
        return 2

    if args.mode == "inprocess":
        report = _run_inprocess_kis(queries, top_k=args.top_k, warmup=args.warmup)
    else:
        report = _run_http_kis(
            queries,
            base_url=args.base_url,
            top_k=args.top_k,
            warmup=args.warmup,
        )

    report["sla"] = _evaluate_sla(report, args.sla_ms)
    print(json.dumps(report, indent=2))

    return 0 if report["sla"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
