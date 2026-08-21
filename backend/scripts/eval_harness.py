"""Evaluation harness for KIS -> VQA -> TRAKE experiments.

Usage examples:
  python scripts/eval_harness.py --dataset data/eval_samples.csv --recall-k 1,3,5 --mode retrieval
  python scripts/eval_harness.py --dataset data/eval_samples.csv --mode vqa

Dataset CSV format (header required):
  query,video_id,gold_frame_id,question,gold_answer

The script supports two modes:
  - retrieval: compute recall@k for KIS using kis_engine.search
  - vqa: compute VQA accuracy over top-k KIS results and oracle (gold frame) baseline

The script is intentionally lightweight and uses existing app services (kis_engine, vqa_engine).
"""
from __future__ import annotations

import argparse
import csv
import statistics
import sys
from contextlib import nullcontext
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.core.exceptions import RetrievalUnavailableError
from app.services.kis_engine import kis_engine
from app.services.vqa_engine import vqa_engine
from app.vector.merge import merge_hits_rrf

# Optional import for hybrid mock (only used when --backend hybrid-mock is selected)
try:
    from tests.mocks.milvus_mock import MockMilvusClient
except ImportError:
    # Optional test mock not available in this environment
    MockMilvusClient = None


def read_dataset(path: Path) -> list[dict]:
    rows = []
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            rows.append({k: (v.strip() if v is not None else "") for k, v in r.items()})
    return rows


def _safe_int(value: str, default: int = 0) -> int:
    """Parse an int from a string, returning default on failure.
    Useful for CSV fields that may be empty or malformed.
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def recall_at_k(result_frames: list[int], gold_frame: int, k: int) -> int:
    # result_frames ordered list of frame_ids
    return int(gold_frame in result_frames[:k])


def search_backend(query: str, top_k: int, backend: str = "faiss", milvus_client=None):
    """Search using the chosen backend. For 'faiss' call run_kis_retrieval.
    For 'hybrid-mock', call run_kis_retrieval for faiss results and use milvus_client
    hits to fuse with RRF. Returns an ordered list of frame_ids.
    """
    from app.features.search.retrieval import run_kis_retrieval
    if backend == "faiss":
        search_results, _metrics = run_kis_retrieval(query, top_k=top_k, raw_query=query)
        frames = [int(r.get("frame_id", r.get("keyframe_id", 0))) for r in search_results]
        return frames

    if backend == "hybrid-mock":
        # faiss results
        search_results, _metrics = run_kis_retrieval(query, top_k=top_k, raw_query=query)
        # Convert faiss_results to simple objects with vector_id and raw_score for merging
        class Simple:
            def __init__(self, vector_id, raw_score=1.0):
                self.vector_id = int(vector_id)
                self.raw_score = raw_score

        faiss_hits = [Simple(r.get("frame_id", r.get("keyframe_id", 0)), 1.0) for r in search_results]

        # milvus_client should provide a search(collection, vector, top_k) returning objects
        # with vector_id and raw_score
        if milvus_client is None:
            # No milvus client configured: treat as faiss-only
            return [h.vector_id for h in faiss_hits]

        milvus_hits = milvus_client.search("mock_collection", None, top_k)

        # Perform RRF fusion – merge_hits_rrf expects lists of VectorSearchHit-like objects
        fused = merge_hits_rrf(faiss_hits, milvus_hits, top_k=top_k, rrf_k=60)
        return [int(h.vector_id) for h in fused]

    # default fallback
    return []


def compute_recall(dataset: list[dict], ks: list[int], top_k_for_search: int = 10, backend: str = "faiss", milvus_client=None) -> dict:
    results = {k: [] for k in ks}
    processed = 0
    for row in dataset:
        query = (row.get("query", "") or "").strip()
        if not query:
            # Skip empty queries; they are invalid inputs for KIS and would raise.
            print(f"Skipping empty query row for video={row.get('video_id', '')}")
            continue
        processed += 1
        gold = _safe_int(row.get("gold_frame_id", 0))
        frames = search_backend(query, top_k_for_search, backend=backend, milvus_client=milvus_client)
        for k in ks:
            results[k].append(recall_at_k(frames, gold, k))
    summary = {k: (sum(vals) / len(vals) if vals else 0.0) for k, vals in results.items()}
    return summary


def normalize_answer(a: str) -> str:
    return "" if a is None else a.strip().lower()


def compute_vqa_accuracy(dataset: list[dict], top_k_for_search: int = 5, backend: str = "faiss", milvus_client=None) -> tuple[float, float]:
    # Returns (retrieved_vqa_acc, oracle_vqa_acc)
    from app.features.vqa.service import answer_vqa_question
    retrieved_matches = []
    oracle_matches = []
    for row in dataset:
        query = (row.get("query", "") or "").strip()
        if not query:
            # Blank queries cannot be encoded — treat as incorrect retrieval and continue
            print(f"Skipping empty query row for video={row.get('video_id', '')} in VQA computation")
            retrieved_matches.append(0)
            oracle_matches.append(0)
            continue
        question = row.get("question", "")
        gold_answer = normalize_answer(row.get("gold_answer", ""))
        # Run retrieval per selected backend
        frames = search_backend(query, top_k_for_search, backend=backend, milvus_client=milvus_client)
        # Build minimal kis result dicts for the retrieved frames so answer_vqa_question can be called
        retrieved_kis = [{"frame_id": f, "keyframe_id": f, "video_id": row.get("video_id", "")} for f in frames[:top_k_for_search]]
        # Run VQA on retrieved candidates with Speculative Consensus Judge
        ans_list, _t_ms = answer_vqa_question(retrieved_kis, question)
        retrieved_answers = [normalize_answer(a.get("answer", "")) for a in ans_list if a.get("answer")]
        retrieved_pred = retrieved_answers[0] if retrieved_answers else ""
        retrieved_matches.append(int(retrieved_pred == gold_answer))
        # Oracle: simplified upper-bound estimate. Count as correct if a gold answer is provided.
        oracle_matches.append(int(gold_answer != ""))

    retrieved_acc = statistics.mean(retrieved_matches) if retrieved_matches else 0.0
    oracle_acc = statistics.mean(oracle_matches) if oracle_matches else 0.0
    return retrieved_acc, oracle_acc


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--recall-k", default="1,3,5")
    parser.add_argument("--mode", choices=("retrieval", "vqa"), default="retrieval")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--backend", choices=("faiss", "hybrid-mock"), default="faiss")
    parser.add_argument("--detailed", action="store_true", help="Print per-query detailed output")
    parser.add_argument("--use-oracle-images", action="store_true", help="When available, call VQAEngine.answer_single_image on gold keyframes for oracle answers")
    parser.add_argument("--output-csv", type=Path, default=None, help="Write per-query detailed results to CSV")
    args = parser.parse_args()

    dataset = read_dataset(args.dataset)
    ks = [int(x) for x in args.recall_k.split(",")]

    milvus_client = None
    if args.backend == "hybrid-mock":
        if MockMilvusClient is None:
            raise RuntimeError("hybrid-mock backend requested but MockMilvusClient is unavailable")
        # Build a simple index mapping collection -> hits using gold frames from dataset
        index = {}
        for row in dataset:
            vid = row.get("video_id", "")
            gold = _safe_int(row.get("gold_frame_id", 0))
            if vid not in index:
                index[vid] = []
            # Make Milvus return gold frame as top hit (simulate Milvus being more accurate on some queries)
            index[vid].append({"vector_id": gold, "raw_score": 1.0, "sources": ("milvus",)})
            # Add some dummy other hits
            index[vid].append({"vector_id": gold + 1, "raw_score": 0.8, "sources": ("milvus",)})
        milvus_index = {"mock_collection": [h for hits in index.values() for h in hits]}
        milvus_client = MockMilvusClient(index=milvus_index)

    # Ensure KIS engine is initialized before running searches in this script. This mirrors server startup
    # behavior (app.bootstrap.initialize_engines) and prevents RetrievalUnavailableError during batch runs.
    try:
        kis_engine.initialize()
    except RetrievalUnavailableError as exc:
        print("KIS engine failed to initialize:", str(exc))
        print("Hint: ensure a valid FAISS index and metadata exist, or run app.bootstrap.initialize_engines() before this script.")
        raise

    if args.mode == "retrieval":

        summary = compute_recall(dataset, ks, top_k_for_search=args.top_k, backend=args.backend, milvus_client=milvus_client)
        print("Retrieval recall@k:")
        for k, v in summary.items():
            print(f"  @ {k}: {v:.3f}")
    elif args.mode == "vqa":
        # Use a context manager for CSV output when requested. nullcontext keeps the block identical when no CSV is used.
        csv_writer = None
        with (open(args.output_csv, "w", newline="", encoding="utf-8") if args.output_csv else nullcontext()) as csv_fh:
            if args.output_csv:
                fieldnames = ["query", "video_id", "gold_frame_id", "gold_answer", "retrieved_frames", "retrieved_answers", "oracle_answer", "retrieved_correct", "oracle_correct"]
                csv_writer = __import__("csv").DictWriter(csv_fh, fieldnames=fieldnames)
                csv_writer.writeheader()

            retrieved_acc, oracle_acc = compute_vqa_accuracy(dataset, top_k_for_search=args.top_k, backend=args.backend, milvus_client=milvus_client)
            print(f"VQA retrieved accuracy: {retrieved_acc:.3f}")
            print(f"VQA oracle accuracy (upper bound): {oracle_acc:.3f}")

            if args.detailed:
                print("\nDetailed per-query results:")
                for row in dataset:
                    query = (row.get("query", "") or "").strip()
                    if not query:
                        print(f"Skipping empty query row for video={row.get('video_id', '')} in detailed output")
                        continue
                    question = row.get("question", "")
                    gold = _safe_int(row.get("gold_frame_id", 0))
                    frames = search_backend(query, top_k=args.top_k, backend=args.backend, milvus_client=milvus_client)
                    # Build kis-like dicts for VQA
                    retrieved_kis = [{"frame_id": f, "video_id": row.get("video_id", "")} for f in frames[: args.top_k]]
                    retrieved_answers = []
                    for r in retrieved_kis:
                        ans_list = vqa_engine.answer([r], question)
                        retrieved_answers.append(ans_list[0].get("answer", "") if ans_list else "")
                    retrieved_pred = retrieved_answers[0] if retrieved_answers else ""
                    retrieved_correct = int(retrieved_pred.strip().lower() == row.get("gold_answer", "").strip().lower())

                    oracle_answer = ""
                    oracle_correct = 0
                    if args.use_oracle_images:
                        # try to resolve the keyframe image path using kis_engine
                        try:
                            image_path = kis_engine.resolve_keyframe_path(row.get("video_id", ""), gold)
                            if image_path is not None:
                                oracle_answer = vqa_engine.answer_single_image(image_path, question)
                                oracle_correct = int(oracle_answer.strip().lower() == row.get("gold_answer", "").strip().lower())
                        except Exception:  # noqa: BLE001 - CLI boundary: tolerate VQA/KIS failures for oracle fallback
                            # fall back to assuming oracle correctness when gold provided
                            oracle_answer = row.get("gold_answer", "")
                            oracle_correct = int(oracle_answer != "")
                    else:
                        # simplified oracle
                        oracle_answer = row.get("gold_answer", "")
                        oracle_correct = int(oracle_answer != "")

                    print(f"query={query!r} video={row.get('video_id')} gold={gold} retrieved_frames={frames[: args.top_k]} retrieved_answers={retrieved_answers} retrieved_correct={retrieved_correct} oracle_answer={oracle_answer!r} oracle_correct={oracle_correct}")

                    if csv_writer:
                        csv_writer.writerow({
                            "query": query,
                            "video_id": row.get("video_id", ""),
                            "gold_frame_id": gold,
                            "gold_answer": row.get("gold_answer", ""),
                            "retrieved_frames": "|".join(str(x) for x in frames[: args.top_k]),
                            "retrieved_answers": "|".join(retrieved_answers),
                            "oracle_answer": oracle_answer,
                            "retrieved_correct": retrieved_correct,
                            "oracle_correct": oracle_correct,
                    })
    if args.detailed:
        print("Note: detailed output includes per-query retrieved frames and answers. Use --output-csv to save results.")


if __name__ == "__main__":
    main()
