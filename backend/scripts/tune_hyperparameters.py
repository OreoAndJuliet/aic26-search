"""Auto-Tuning Engine for AIC 2026 Retrieval Hyperparameters.

Runs systematic grid/random search over algorithmic knobs against the ground-truth dataset,
ranks configurations by official Codabench Mean-of-Top-k-max-R@k score,
and optionally applies the best parameters directly to .env.
"""

from __future__ import annotations

import argparse
import asyncio
import itertools
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Ensure UTF-8 output encoding on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Ensure project root is in sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Setup logging
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger("autotune")


@dataclass
class HyperparameterConfig:
    name: str
    ensemble_enabled: bool = True
    ensemble_primary_weight: float = 0.60
    ensemble_secondary_weight: float = 0.40
    crop_enabled: bool = True
    crop_topk: int = 15
    crop_weight: float = 0.25
    visual_prf_enabled: bool = True
    visual_prf_weight: float = 0.20
    temporal_consensus_enabled: bool = True
    temporal_consensus_boost: float = 0.15
    temporal_smoothing_enabled: bool = True
    temporal_smoothing_weight: float = 0.15
    diversification_enabled: bool = True
    diversification_max_per_vid: int = 3
    concept_decomp_enabled: bool = True
    concept_weight_global: float = 0.40
    concept_weight_entity: float = 0.30
    concept_weight_attr: float = 0.15
    object_rerank_enabled: bool = True
    object_rerank_weight: float = 0.10
    mediainfo_rerank_enabled: bool = True
    mediainfo_rerank_weight: float = 0.15


@dataclass
class TuningResult:
    config: HyperparameterConfig
    official_mean_score: float = 0.0
    r_at_1: float = 0.0
    r_at_5: float = 0.0
    r_at_20: float = 0.0
    r_at_50: float = 0.0
    r_at_100: float = 0.0
    kis_r10: float = 0.0
    vqa_acc: float = 0.0
    trake_acc: float = 0.0
    mean_latency_ms: float = 0.0


def apply_config_to_runtime(cfg: HyperparameterConfig) -> None:
    """Temporarily patch runtime settings and engines."""
    from app.core.config import settings
    from app.services.kis_engine import kis_engine
    from app.providers.text_encoder import create_text_encoder

    object.__setattr__(settings, "TEXT_ENCODER_ENSEMBLE_ENABLED", cfg.ensemble_enabled)
    object.__setattr__(settings, "ENSEMBLE_PRIMARY_WEIGHT", cfg.ensemble_primary_weight)
    object.__setattr__(settings, "ENSEMBLE_SECONDARY_WEIGHT", cfg.ensemble_secondary_weight)
    object.__setattr__(settings, "KIS_CROP_ALIGNMENT_ENABLED", cfg.crop_enabled)
    object.__setattr__(settings, "KIS_CROP_ALIGNMENT_TOPK", cfg.crop_topk)
    object.__setattr__(settings, "KIS_CROP_ALIGNMENT_WEIGHT", cfg.crop_weight)
    object.__setattr__(settings, "VISUAL_PRF_ENABLED", cfg.visual_prf_enabled)
    object.__setattr__(settings, "VISUAL_PRF_WEIGHT", cfg.visual_prf_weight)
    object.__setattr__(settings, "TEMPORAL_CONSENSUS_ENABLED", cfg.temporal_consensus_enabled)
    object.__setattr__(settings, "TEMPORAL_CONSENSUS_BOOST_WEIGHT", cfg.temporal_consensus_boost)
    object.__setattr__(settings, "TEMPORAL_SMOOTHING_ENABLED", cfg.temporal_smoothing_enabled)
    object.__setattr__(settings, "TEMPORAL_SMOOTHING_WEIGHT", cfg.temporal_smoothing_weight)
    object.__setattr__(settings, "DIVERSIFICATION_ENABLED", cfg.diversification_enabled)
    object.__setattr__(settings, "DIVERSIFICATION_MAX_PER_VIDEO", cfg.diversification_max_per_vid)
    object.__setattr__(settings, "MULTI_CONCEPT_DECOMPOSITION_ENABLED", cfg.concept_decomp_enabled)
    object.__setattr__(settings, "MULTI_CONCEPT_WEIGHT_GLOBAL", cfg.concept_weight_global)
    object.__setattr__(settings, "MULTI_CONCEPT_WEIGHT_ENTITY", cfg.concept_weight_entity)
    object.__setattr__(settings, "MULTI_CONCEPT_WEIGHT_ATTRIBUTE", cfg.concept_weight_attr)
    object.__setattr__(settings, "KIS_OBJECT_RERANK_ENABLED", cfg.object_rerank_enabled)
    object.__setattr__(settings, "KIS_OBJECT_RERANK_WEIGHT", cfg.object_rerank_weight)
    object.__setattr__(settings, "KIS_MEDIA_INFO_RERANK_ENABLED", cfg.mediainfo_rerank_enabled)
    object.__setattr__(settings, "KIS_MEDIA_INFO_RERANK_WEIGHT", cfg.mediainfo_rerank_weight)

    # Update text encoder if ensemble changed
    try:
        kis_engine.text_encoder = create_text_encoder(
            provider=settings.TEXT_ENCODER_PROVIDER,
            model_name=settings.CLIP_MODEL_NAME,
            ensemble_enabled=cfg.ensemble_enabled,
            ensemble_model_name=settings.ENSEMBLE_MODEL_NAME,
            ensemble_primary_weight=cfg.ensemble_primary_weight,
            ensemble_secondary_weight=cfg.ensemble_secondary_weight,
            fallback_to_mock=settings.TEXT_ENCODER_FALLBACK_TO_MOCK,
        )
    except Exception as exc:
        logger.warning("Could not re-create encoder: %s", exc)


_TRANSLATION_CACHE: dict[str, str] = {}


async def evaluate_single_config(
    cfg: HyperparameterConfig,
    queries: list[dict[str, Any]],
    tolerance_seconds: float = 30.0,
    top_k: int = 100,
) -> TuningResult:
    """Evaluate a hyperparameter config in-process across all queries."""
    from app.features.search.service import run_search
    from app.services.translator import translator

    apply_config_to_runtime(cfg)

    # Pre-cache translations to prevent API rate limits during tuning iterations
    for q in queries:
        t_text = q.get("query", "")
        if t_text and t_text not in _TRANSLATION_CACHE:
            try:
                res = await translator.translate_async(t_text)
                _TRANSLATION_CACHE[t_text] = res.text
            except Exception:
                _TRANSLATION_CACHE[t_text] = t_text

    r1_sum = 0.0
    r5_sum = 0.0
    r20_sum = 0.0
    r50_sum = 0.0
    r100_sum = 0.0
    kis_r10_hits = 0
    kis_total = 0
    vqa_hits = 0
    vqa_total = 0
    trake_hits = 0
    trake_total = 0
    latencies = []

    for q in queries:
        q_type = q.get("task_type", "KIS")
        q_text = q.get("query", "")
        exp_vid = q.get("expected_video_id", "")
        exp_ts = float(q.get("expected_timestamp", 0.0))
        acceptable_vids = set(q.get("acceptable_video_ids", [exp_vid]))

        start_t = time.perf_counter()
        try:
            if q_type == "TRAKE":
                res = await run_search(
                    task_type="TRAKE",
                    query=q_text,
                    question=None,
                    top_k=top_k,
                    events=q.get("events", []),
                )
            elif q_type == "VQA":
                res = await run_search(
                    task_type="VQA",
                    query=q_text,
                    question=q.get("question", ""),
                    top_k=top_k,
                )
            else:
                res = await run_search(
                    task_type="KIS",
                    query=q_text,
                    question=None,
                    top_k=top_k,
                )
        except Exception as exc:
            logger.warning("Query failed: %s - %s", q.get("query_id"), exc)
            res = {"results": []}

        elapsed_ms = (time.perf_counter() - start_t) * 1000
        latencies.append(elapsed_ms)

        items = res.get("results", [])

        # KIS Metric
        if q_type == "KIS":
            kis_total += 1
            rank_found = None
            for idx, it in enumerate(items, start=1):
                vid = str(it.get("video_id", ""))
                ts = float(it.get("timestamp", 0.0))
                if vid in acceptable_vids and (exp_ts <= 0.0 or abs(ts - exp_ts) <= tolerance_seconds):
                    rank_found = idx
                    break

            r1 = 1.0 if (rank_found is not None and rank_found <= 1) else 0.0
            r5 = 1.0 if (rank_found is not None and rank_found <= 5) else 0.0
            r20 = 1.0 if (rank_found is not None and rank_found <= 20) else 0.0
            r50 = 1.0 if (rank_found is not None and rank_found <= 50) else 0.0
            r100 = 1.0 if (rank_found is not None and rank_found <= 100) else 0.0

            if rank_found is not None and rank_found <= 10:
                kis_r10_hits += 1

            r1_sum += r1
            r5_sum += r5
            r20_sum += r20
            r50_sum += r50
            r100_sum += r100

        # VQA Metric
        elif q_type == "VQA":
            vqa_total += 1
            ans = str(items[0].get("answer", "")).lower() if items else ""
            exp_ans = str(q.get("expected_answer", "")).lower()
            acc_ans = [a.lower() for a in q.get("acceptable_answers", [exp_ans])]
            correct = any(acc in ans for acc in acc_ans) if ans else False
            val = 1.0 if correct else 0.0
            if correct:
                vqa_hits += 1
            r1_sum += val
            r5_sum += val
            r20_sum += val
            r50_sum += val
            r100_sum += val

        # TRAKE Metric
        elif q_type == "TRAKE":
            trake_total += 1
            if len(items) >= 2:
                timestamps = [float(it.get("timestamp", 0.0)) for it in items]
                video_ids = [str(it.get("video_id", "")) for it in items]
                mono = (len(set(video_ids)) == 1) and all(timestamps[i] < timestamps[i + 1] for i in range(len(timestamps) - 1))
            else:
                mono = False
            val = 1.0 if mono else 0.0
            if mono:
                trake_hits += 1
            r1_sum += val
            r5_sum += val
            r20_sum += val
            r50_sum += val
            r100_sum += val

    n = len(queries)
    if n == 0:
        return TuningResult(config=cfg)

    r_at_1 = r1_sum / n
    r_at_5 = r5_sum / n
    r_at_20 = r20_sum / n
    r_at_50 = r50_sum / n
    r_at_100 = r100_sum / n
    official_mean = (r_at_1 + r_at_5 + r_at_20 + r_at_50 + r_at_100) / 5.0

    return TuningResult(
        config=cfg,
        official_mean_score=official_mean,
        r_at_1=r_at_1,
        r_at_5=r_at_5,
        r_at_20=r_at_20,
        r_at_50=r_at_50,
        r_at_100=r_at_100,
        kis_r10=(kis_r10_hits / kis_total) if kis_total > 0 else 0.0,
        vqa_acc=(vqa_hits / vqa_total) if vqa_total > 0 else 0.0,
        trake_acc=(trake_hits / trake_total) if trake_total > 0 else 0.0,
        mean_latency_ms=sum(latencies) / len(latencies) if latencies else 0.0,
    )


def generate_search_candidates(mode: str) -> list[HyperparameterConfig]:
    """Generate search candidates based on the chosen mode."""
    if mode == "presets":
        return [
            HyperparameterConfig(
                name="Preset 1: Competition Winner (Max Accuracy)",
                ensemble_enabled=True,
                ensemble_primary_weight=0.60,
                ensemble_secondary_weight=0.40,
                crop_enabled=True,
                crop_topk=15,
                crop_weight=0.25,
                visual_prf_enabled=True,
                visual_prf_weight=0.20,
                temporal_consensus_enabled=True,
                temporal_consensus_boost=0.15,
                temporal_smoothing_enabled=True,
                temporal_smoothing_weight=0.15,
                diversification_enabled=True,
                diversification_max_per_vid=3,
                concept_decomp_enabled=True,
                concept_weight_global=0.40,
                concept_weight_entity=0.30,
            ),
            HyperparameterConfig(
                name="Preset 2: Ultra Fast Low Latency",
                ensemble_enabled=False,
                ensemble_primary_weight=1.0,
                crop_enabled=False,
                crop_topk=0,
                crop_weight=0.0,
                visual_prf_enabled=False,
                visual_prf_weight=0.0,
                temporal_consensus_enabled=False,
                temporal_consensus_boost=0.0,
                temporal_smoothing_enabled=False,
                diversification_enabled=True,
                diversification_max_per_vid=5,
                concept_decomp_enabled=False,
            ),
            HyperparameterConfig(
                name="Preset 3: Vietnamese Culture Focus",
                ensemble_enabled=True,
                ensemble_primary_weight=0.40,
                ensemble_secondary_weight=0.60,
                crop_enabled=True,
                crop_topk=15,
                crop_weight=0.30,
                visual_prf_enabled=True,
                visual_prf_weight=0.25,
                temporal_consensus_enabled=True,
                temporal_consensus_boost=0.20,
                temporal_smoothing_enabled=True,
                temporal_smoothing_weight=0.18,
                diversification_enabled=True,
                diversification_max_per_vid=3,
                concept_decomp_enabled=True,
                concept_weight_global=0.35,
                concept_weight_entity=0.35,
            ),
        ]

    # Grid search space
    candidates = []
    
    # 1. Ensemble weights (Primary vs Secondary)
    ensemble_opts = [(True, 0.7, 0.3), (True, 0.6, 0.4), (True, 0.5, 0.5), (False, 1.0, 0.0)]
    # 2. Crop topk and weight
    crop_opts = [(True, 15, 0.25), (True, 10, 0.20), (False, 0, 0.0)]
    # 3. Visual PRF
    prf_opts = [(True, 0.20), (True, 0.10), (False, 0.0)]
    # 4. Temporal consensus
    cons_opts = [(True, 0.15), (False, 0.0)]
    # 5. Diversification
    div_opts = [3, 4]

    idx = 1
    for ens, crop, prf, cons, div in itertools.product(ensemble_opts, crop_opts, prf_opts, cons_opts, div_opts):
        c = HyperparameterConfig(
            name=f"Config-{idx:02d}",
            ensemble_enabled=ens[0],
            ensemble_primary_weight=ens[1],
            ensemble_secondary_weight=1.0 - ens[1] if ens[0] else 0.0,
            crop_enabled=crop[0],
            crop_topk=crop[1],
            crop_weight=crop[2],
            visual_prf_enabled=prf[0],
            visual_prf_weight=prf[1],
            temporal_consensus_enabled=cons[0],
            temporal_consensus_boost=cons[1],
            temporal_smoothing_enabled=True,
            temporal_smoothing_weight=0.15,
            diversification_enabled=True,
            diversification_max_per_vid=div,
        )
        candidates.append(c)
        idx += 1

    if mode == "fast_grid":
        return candidates[:12]  # Test top 12 representative configurations

    return candidates


def apply_winner_to_env(winner: HyperparameterConfig, env_path: Path) -> None:
    """Safely rewrite .env with champion parameters."""
    if not env_path.is_file():
        logger.error(".env file not found at %s", env_path)
        return

    content = env_path.read_text(encoding="utf-8")

    replacements = {
        "TEXT_ENCODER_ENSEMBLE_ENABLED": str(winner.ensemble_enabled).lower(),
        "ENSEMBLE_PRIMARY_WEIGHT": f"{winner.ensemble_primary_weight:.2f}",
        "ENSEMBLE_SECONDARY_WEIGHT": f"{winner.ensemble_secondary_weight:.2f}",
        "KIS_CROP_ALIGNMENT_ENABLED": str(winner.crop_enabled).lower(),
        "KIS_CROP_ALIGNMENT_TOPK": str(winner.crop_topk),
        "KIS_CROP_ALIGNMENT_WEIGHT": f"{winner.crop_weight:.2f}",
        "VISUAL_PRF_ENABLED": str(winner.visual_prf_enabled).lower(),
        "VISUAL_PRF_WEIGHT": f"{winner.visual_prf_weight:.2f}",
        "TEMPORAL_CONSENSUS_ENABLED": str(winner.temporal_consensus_enabled).lower(),
        "TEMPORAL_CONSENSUS_BOOST_WEIGHT": f"{winner.temporal_consensus_boost:.2f}",
        "TEMPORAL_SMOOTHING_ENABLED": str(winner.temporal_smoothing_enabled).lower(),
        "TEMPORAL_SMOOTHING_WEIGHT": f"{winner.temporal_smoothing_weight:.2f}",
        "DIVERSIFICATION_ENABLED": str(winner.diversification_enabled).lower(),
        "DIVERSIFICATION_MAX_PER_VIDEO": str(winner.diversification_max_per_vid),
        "MULTI_CONCEPT_DECOMPOSITION_ENABLED": str(winner.concept_decomp_enabled).lower(),
        "MULTI_CONCEPT_WEIGHT_GLOBAL": f"{winner.concept_weight_global:.2f}",
        "MULTI_CONCEPT_WEIGHT_ENTITY": f"{winner.concept_weight_entity:.2f}",
        "MULTI_CONCEPT_WEIGHT_ATTRIBUTE": f"{winner.concept_weight_attr:.2f}",
    }

    for key, val in replacements.items():
        pattern = rf"^{key}\s*=.*$"
        if re.search(pattern, content, flags=re.MULTILINE):
            content = re.sub(pattern, f"{key}={val}", content, flags=re.MULTILINE)
        else:
            content += f"\n{key}={val}"

    env_path.write_text(content, encoding="utf-8")
    print(f"\n[SUCCESS] Champion parameters automatically written to {env_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="AIC 2026 Retrieval Hyperparameter Auto-Tuner")
    parser.add_argument("--mode", choices=["presets", "fast_grid", "full_grid"], default="presets", help="Search space mode")
    parser.add_argument("--suite", choices=["all", "kis", "vqa", "trake"], default="all", help="Task suite to tune on")
    parser.add_argument("--dataset", default="data/mock_contest_ground_truth.json", help="Path to evaluation ground truth JSON")
    parser.add_argument("--apply", action="store_true", help="Automatically write champion parameters to .env")
    parser.add_argument("--topk", type=int, default=100, help="Top-K candidates per query")
    parser.add_argument("--tolerance", type=float, default=30.0, help="Temporal tolerance window in seconds")
    args = parser.parse_args()

    gt_file = REPO_ROOT / args.dataset
    if not gt_file.is_file():
        print(f"Error: Dataset not found at {gt_file}", file=sys.stderr)
        sys.exit(1)

    gt_data = json.loads(gt_file.read_text(encoding="utf-8"))
    all_queries = gt_data.get("queries", [])
    if args.suite and args.suite.upper() != "ALL":
        queries = [q for q in all_queries if q.get("task_type", "").upper() == args.suite.upper()]
    else:
        queries = all_queries

    print("=================================================================")
    print("      AIC 2026 RETRIEVAL HYPERPARAMETER AUTO-TUNER               ")
    print("=================================================================")
    print(f"  Mode:            {args.mode.upper()}")
    print(f"  Suite:           {args.suite.upper()}")
    print(f"  Dataset:         {args.dataset} ({len(queries)} queries)")
    print(f"  Tolerance:       ±{args.tolerance}s")
    print(f"  Auto-Apply .env: {args.apply}")
    print("-----------------------------------------------------------------")
    print("  Initializing AI engines & vector indexes (one-time warmup)...")
    from app.bootstrap import initialize_engines
    initialize_engines()
    print("  All AI engines initialized successfully!\n")

    candidates = generate_search_candidates(args.mode)
    print(f"  Exploring {len(candidates)} candidate parameter configuration(s)...\n")

    results: list[TuningResult] = []

    for i, cfg in enumerate(candidates, start=1):
        sys.stdout.write(f"[{i:02d}/{len(candidates):02d}] Evaluating: {cfg.name} ... ")
        sys.stdout.flush()

        res = asyncio.run(evaluate_single_config(cfg, queries, args.tolerance, args.topk))
        results.append(res)

        print(f"Score={res.official_mean_score:.4f} | R@1={res.r_at_1*100:.1f}% | R@5={res.r_at_5*100:.1f}% | Latency={res.mean_latency_ms:.1f}ms")

    # Sort results by official score descending, then by latency ascending
    results.sort(key=lambda r: (r.official_mean_score, r.r_at_1, -r.mean_latency_ms), reverse=True)

    print("\n=================================================================")
    print("                LEADERBOARD - RANKED RESULTS                     ")
    print("=================================================================")
    print(f"{'Rank':<5} {'Config Name':<32} {'Score':<8} {'R@1':<7} {'R@5':<7} {'R@20':<7} {'KIS R10':<9} {'Lat(ms)':<8}")
    print("-" * 88)

    for rank, res in enumerate(results, start=1):
        badge = "🏆" if rank == 1 else f"#{rank:<2}"
        print(
            f"{badge:<5} {res.config.name:<32} {res.config.name[:0]}{res.official_mean_score:>6.4f} "
            f"{res.r_at_1*100:>5.1f}% {res.r_at_5*100:>5.1f}% {res.r_at_20*100:>5.1f}% "
            f"{res.kis_r10*100:>7.1f}% {res.mean_latency_ms:>7.1f}ms"
        )

    winner = results[0]
    print("\n=================================================================")
    print(f"  🏆 CHAMPION CONFIGURATION: {winner.config.name}")
    print("=================================================================")
    print(f"  Official Mean Score:   {winner.official_mean_score:.6f}")
    print(f"  R@1 (Exact Top-1 Hit): {winner.r_at_1*100:.1f}%")
    print(f"  R@5 (Top-5 Recall):    {winner.r_at_5*100:.1f}%")
    print(f"  R@20:                  {winner.r_at_20*100:.1f}%")
    print(f"  KIS Top-10 Recall:     {winner.kis_r10*100:.1f}%")
    print(f"  TRAKE Alignment:       {winner.trake_acc*100:.1f}%")
    print(f"  VQA Accuracy:          {winner.vqa_acc*100:.1f}%")
    print(f"  Mean Latency:          {winner.mean_latency_ms:.2f} ms")
    print("-----------------------------------------------------------------")
    print("  Parameters:")
    print(f"    - Ensemble Enabled:        {winner.config.ensemble_enabled} (Pri={winner.config.ensemble_primary_weight:.2f}, Sec={winner.config.ensemble_secondary_weight:.2f})")
    print(f"    - Crop Regional Alignment: {winner.config.crop_enabled} (TopK={winner.config.crop_topk}, Weight={winner.config.crop_weight:.2f})")
    print(f"    - Temporal Smoothing:      {winner.config.temporal_smoothing_enabled} (Weight={winner.config.temporal_smoothing_weight:.2f})")
    print(f"    - Video Diversification:   Max {winner.config.diversification_max_per_vid} frames/video")
    print("=================================================================")

    if args.apply:
        apply_winner_to_env(winner.config, REPO_ROOT / ".env")
    else:
        print("\nTo apply these optimal settings automatically, run:")
        print(f"  python scripts/tune_hyperparameters.py --mode {args.mode} --apply")
        print("  or: .\\tune.ps1 -Apply")


if __name__ == "__main__":
    main()
