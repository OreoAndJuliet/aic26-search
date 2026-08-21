"""Load and sample competition query batches."""

from __future__ import annotations

import csv
import random
from pathlib import Path
from typing import Any

from app.core.config import settings


def load_query_batch(path: Path | str) -> list[dict[str, Any]]:
    csv_path = Path(path)
    with csv_path.open("r", encoding="utf-8", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        if not reader.fieldnames or "id" not in reader.fieldnames:
            raise ValueError("Query file must contain an id column.")

        rows: list[dict[str, Any]] = []
        for row in reader:
            query_id = int(row["id"])
            task_type = (row.get("type") or "KIS").strip().upper()
            events_raw = (row.get("events") or "").strip()
            events = [part.strip() for part in events_raw.split("|") if part.strip()]
            rows.append(
                {
                    "id": query_id,
                    "type": task_type,
                    "query": (row.get("query") or row.get("text") or "").strip(),
                    "question": (row.get("question") or "").strip() or None,
                    "events": events,
                    "top_k": min(int(row.get("top_k") or settings.MAX_TOP_K), settings.MAX_TOP_K),
                    "top_k_per_event": int(row.get("top_k_per_event") or 20),
                }
            )
    return rows


def load_query_text_map(path: Path | str) -> dict[int, str]:
    """Return query id → text for grading scripts that only need id/query pairs."""
    return {int(item["id"]): item["query"] for item in load_query_batch(path)}


def sample_queries(
    queries: list[dict[str, Any]],
    *,
    fraction: float,
    seed: int = 42,
) -> list[dict[str, Any]]:
    """Deterministically sample a subset of queries (e.g. 50% mock-competition drill)."""
    if fraction >= 1.0:
        return list(queries)
    if fraction <= 0:
        raise ValueError("sample fraction must be greater than 0.")

    count = max(1, round(len(queries) * fraction))
    rng = random.Random(seed)
    sampled = rng.sample(queries, min(count, len(queries)))
    return sorted(sampled, key=lambda item: int(item["id"]))


def merge_queries_with_groundtruth_types(
    queries: list[dict[str, Any]],
    ground_truth_rows: list[Any],
) -> list[dict[str, Any]]:
    """Fill missing query types from ground-truth labels keyed by query id."""
    type_by_id = {int(row.query_id): str(row.task_type).upper() for row in ground_truth_rows}
    merged: list[dict[str, Any]] = []
    for item in queries:
        copy = dict(item)
        if not copy.get("type") or copy["type"] == "KIS":
            gt_type = type_by_id.get(int(copy["id"]))
            if gt_type:
                copy["type"] = gt_type
        merged.append(copy)
    return merged
