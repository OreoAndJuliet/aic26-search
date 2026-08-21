"""Comprehensive end-to-end unit and integration test suite for AIC 2026 Backend."""

import os
from pathlib import Path
import pytest
import numpy as np
from PIL import Image
import requests

from app.core.config import settings
from app.algorithms.concept_decomposition import (
    decompose_query_concepts,
    build_multiconcept_fused_vector,
    calculate_dynamic_saliency_weights,
)
from app.algorithms.vqa_distillation import (
    clean_conversational_fluff,
    extract_interrogative_target,
    build_saliency_focused_prompt,
)
from app.algorithms.spatial_attention import (
    parse_spatial_quadrant,
    get_spatial_focused_image,
)
from app.algorithms.temporal_vqa import (
    is_dynamic_action_question,
    build_temporal_storyboard,
)
from app.algorithms.visual_zooming import (
    detect_micro_target,
    extract_high_res_object_crop,
)
from app.algorithms.temporal_alignment import (
    EventCandidate,
    align_events_dtw,
    align_topk_events_dtw,
)
from app.algorithms.local_cv_filters import (
    extract_crop_dominant_color,
    estimate_box_posture,
)
from app.utils.async_image_loader import (
    preload_image_async,
    get_cached_or_open_image,
)
from app.cache.visual_hash_cache import (
    compute_dhash,
    hamming_distance,
    lookup_visual_cache,
    store_visual_cache,
)
from app.services.ocr_store import ocr_store
from app.services.object_store import object_store
from app.features.vqa.service import (
    has_visual_attributes,
    parse_counting_target,
    parse_existence_target,
)

BASE_URL = settings.BACKEND_HOST.rstrip("/")


class DummyEncoder:
    def encode(self, text: str) -> np.ndarray:
        vec = np.ones(512, dtype=np.float32)
        norm = np.linalg.norm(vec)
        return vec / norm if norm > 0 else vec


def test_concept_decomposition_parser():
    """Test linguistic decomposition of complex multi-attribute queries."""
    query = "a woman wearing a red jacket walking near a wooden bridge"
    concepts = decompose_query_concepts(query)
    
    assert concepts["global"] == query
    assert "woman" in concepts.get("entity", "").lower()
    assert "red" in concepts.get("attribute", "").lower() or "wearing" in concepts.get("attribute", "").lower()
    assert "walk" in concepts.get("action", "").lower()
    assert "bridge" in concepts.get("scene", "").lower()


def test_concept_decomposition_dynamic_saliency():
    """Test dynamic saliency weighting allocating highest weight to specific modifiers."""
    concepts = {
        "global": "a person wearing a bright yellow raincoat walking on the street",
        "entity": "a person",
        "attribute": "wearing a bright yellow raincoat",
        "action": "walking",
        "scene": "on the street",
    }
    weights = calculate_dynamic_saliency_weights(concepts)
    assert weights["attribute"] > weights["entity"]
    assert weights["attribute"] > weights["scene"]


def test_vqa_distillation_and_prompt_assembly():
    """Test conversational fluff removal and interrogative focus extraction."""
    q_fluff = "Can you please look at the table and tell me what fruit is in the bowl?"
    clean_q = clean_conversational_fluff(q_fluff)
    assert not clean_q.lower().startswith("can you please")
    assert "fruit" in clean_q.lower()

    target = extract_interrogative_target(clean_q)
    assert target == "fruit"

    prompt = build_saliency_focused_prompt(q_fluff)
    assert "Target Focus: FRUIT" in prompt


def test_perceptual_visual_hash_cache():
    """Test fast 64-bit dHash and perceptual caching."""
    arr = np.linspace(0, 255, 64 * 64, dtype=np.uint8).reshape((64, 64))
    img1 = Image.fromarray(arr, mode="L").convert("RGB")
    h1 = compute_dhash(img1)
    assert isinstance(h1, int)
    assert h1 != 0
    assert hamming_distance(h1, h1) == 0

    store_visual_cache("What color is this?", img1, "blueish")
    ans = lookup_visual_cache("What color is this?", img1, hamming_threshold=2)
    assert ans == "blueish"


def test_dynamic_visual_zooming():
    """Test micro-object detection and high-res crop extraction."""
    assert detect_micro_target("What is the person holding in his cup?") == "cup"
    assert detect_micro_target("What brand is on the watch?") == "watch"
    assert detect_micro_target("What is the general scene?") is None


def test_ocr_store_indexing_and_scoring():
    """Test local OCR and inverted keyword index scoring."""
    ocr_store.build_index()
    terms = ocr_store.extract_text_query_terms("A bus with number 150 and sign 'ABC'")
    assert "150" in terms or "abc" in terms


def test_vietnam_landmarks_gazetteer():
    """Test landmark extraction and enrichment."""
    from app.services.landmark_gazetteer import landmark_gazetteer
    landmark_gazetteer.load()
    lms = landmark_gazetteer.match_landmarks("người đi bộ gần Chợ Bến Thành và Landmark 81")
    assert len(lms) >= 2
    names = [lm["name"] for lm in lms]
    assert "Chợ Bến Thành" in names
    assert "Landmark 81" in names

    enriched = landmark_gazetteer.enrich_query_with_landmarks("người ở Chợ Bến Thành")
    assert "Ben Thanh Market" in enriched


def test_encyclopedic_store_integration():
    """Test full matching across Traffic Signs, Brands, Vehicles, and Landmarks."""
    from app.services.encyclopedic_store import encyclopedic_store
    encyclopedic_store.load_all()
    q = "chiếc xe máy Honda Wave chạy qua biển cấm rẽ trái gần Chợ Bến Thành"
    matches = encyclopedic_store.match_entities_in_query(q)
    assert len(matches) >= 3
    types = [m["entity_type"] for m in matches]
    assert "TrafficSign" in types
    assert "Brand" in types or "Landmark" in types


def test_competition_legality_and_security_compliance():
    """Test that codebase contains 0 hardcoded ground truth maps and 0 leaked secrets."""
    import os, re
    from pathlib import Path

    root = Path(".")
    secret_pats = [r"AIzaSy[A-Za-z0-9\-_]{33}", r"sk-[A-Za-z0-9]{32,}"]
    cheat_pats = [r"query_ground_truth\s*=\s*\{", r"ANSWER_KEYS\s*=\s*\{"]

    violations = []
    skip_dirs = {".venv", ".git", "__pycache__", ".pytest_cache", "static", "objects", "features", "map_keyframes"}
    for rootdir, dirs, files in os.walk("."):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for f in files:
            if f.endswith((".py", ".json", ".csv", ".ps1", ".bat")) and not f.endswith("test_all_features.py"):
                p = Path(rootdir) / f
                text = p.read_text(encoding="utf-8", errors="ignore")
                for pat in secret_pats:
                    if re.search(pat, text) and f != ".env.example":
                        violations.append(f"Secret in {p}")
                for pat in cheat_pats:
                    if re.search(pat, text):
                        violations.append(f"Cheat in {p}")

    assert len(violations) == 0, f"Found integrity violations: {violations}"


def test_concept_decomposition_vector_builder():
    """Test weighted composite vector construction and L2 normalization."""
    encoder = DummyEncoder()
    query = "a woman wearing a red jacket walking near a wooden bridge"
    fused_vec = build_multiconcept_fused_vector(query, encoder)
    
    assert isinstance(fused_vec, np.ndarray)
    assert fused_vec.shape == (512,)
    np.testing.assert_almost_equal(float(np.linalg.norm(fused_vec)), 1.0, decimal=4)


def test_spatial_quadrant_parser():
    """Test directional directive extraction for VQA."""
    q_left = "What is the person on the left side holding?"
    quad, coords = parse_spatial_quadrant(q_left)
    assert quad == "left"
    assert coords is not None
    assert coords[1] == 0.0  # xmin
    assert coords[3] == 0.60  # xmax

    q_tr = "What object is in the top-right corner?"
    quad_tr, coords_tr = parse_spatial_quadrant(q_tr)
    assert quad_tr == "top_right"
    assert coords_tr is not None


def test_temporal_action_detection():
    """Test dynamic action detection for temporal storyboards."""
    assert is_dynamic_action_question("Is the person standing up or sitting down?") is True
    assert is_dynamic_action_question("Is the car entering or leaving the garage?") is True
    assert is_dynamic_action_question("Người đó đang đi vào hay đi ra?") is True
    assert is_dynamic_action_question("What color is the wall?") is False


def test_temporal_storyboard_builder():
    """Test horizontal 3-frame storyboard assembly."""
    sb_path = build_temporal_storyboard("L22_V021", 166, settings.KEYFRAMES_DIR)
    if sb_path is not None:
        assert sb_path.is_file()
        assert sb_path.name.endswith("_storyboard.jpg")


def test_vectorized_dtw_alignment():
    """Test vectorized DTW trajectory matching with Gaussian temporal decay."""
    c1 = EventCandidate("V1", 10, 10.0, 0.8, 0, "event 1", {})
    c2 = EventCandidate("V1", 20, 25.0, 0.85, 1, "event 2", {})
    c3 = EventCandidate("V1", 30, 40.0, 0.9, 2, "event 3", {})

    layers = [[c1], [c2], [c3]]
    res = align_events_dtw(layers, target_gap_seconds=15.0, gap_sigma_seconds=25.0)
    assert res is not None
    path, score = res
    assert len(path) == 3
    assert path[0].timestamp < path[1].timestamp < path[2].timestamp
    assert score > 0.0


def test_local_cv_filters():
    """Test 0-token posture and HSV color classification."""
    standing_box = [0.1, 0.4, 0.9, 0.6]
    assert estimate_box_posture(standing_box) == "standing"

    sitting_box = [0.4, 0.3, 0.8, 0.7]
    assert estimate_box_posture(sitting_box) == "sitting"

    green_img = Image.new("RGB", (50, 50), (20, 210, 30))
    color, conf = extract_crop_dominant_color(green_img)
    assert color == "green"
    assert conf > 0.80


def test_async_image_loader():
    """Test speculative async decoding cache."""
    test_kf = settings.KEYFRAMES_DIR / "L22_V021" / "166.jpg"
    if test_kf.is_file():
        preload_image_async(test_kf)
        img = get_cached_or_open_image(test_kf)
        assert img is not None
        assert isinstance(img, Image.Image)


def test_vqa_counting_router_and_attribute_detection():
    """Test pure count vs visual attribute routing."""
    assert has_visual_attributes("HOW MANY PEOPLE ARE THERE") is False
    assert has_visual_attributes("HOW MANY PEOPLE ARE STANDING") is True
    assert has_visual_attributes("HOW MANY RED CARS") is True

    is_count, target = parse_counting_target("How many people are in the room?")
    assert is_count is True
    assert target.lower() == "person"


def test_scale_aware_local_counting():
    """Test scale-aware counting with dynamic thresholds."""
    res = object_store.count_scale_aware("L22_V011", 115, "Person")
    assert "count" in res
    assert "bboxes" in res
    assert res["count"] >= 0


def test_keyframe_media_serving_endpoint():
    """Test keyframe image retrieval and map_keyframes resolution."""
    from fastapi.testclient import TestClient
    from main import app
    with TestClient(app) as client:
        res = client.get("/keyframes/L22_V021/17625.jpg")
        assert res.status_code == 200
        assert res.headers.get("content-type") == "image/jpeg"
        assert len(res.content) > 1000


def test_search_api_kis():
    """Test KIS search endpoint via TestClient."""
    from fastapi.testclient import TestClient
    from main import app
    with TestClient(app) as client:
        res = client.post("/api/search", json={
            "type": "KIS",
            "query": "kitchen scene",
            "top_k": 3
        })
        assert res.status_code == 200
        data = res.json()
        assert "results" in data
        assert len(data["results"]) <= 3
        assert data["type"] == "KIS"


def test_search_api_vqa():
    """Test VQA search endpoint via TestClient."""
    from fastapi.testclient import TestClient
    from main import app
    with TestClient(app) as client:
        res = client.post("/api/search", json={
            "type": "VQA",
            "query": "kitchen scene",
            "question": "How many chairs are in the room?",
            "top_k": 2
        })
        assert res.status_code == 200
        data = res.json()
        assert "results" in data
        assert len(data["results"]) <= 2
        assert data["type"] == "VQA"
        if data["results"]:
            assert "answer" in data["results"][0]


def test_search_api_trake():
    """Test TRAKE search endpoint via TestClient."""
    from fastapi.testclient import TestClient
    from main import app
    with TestClient(app) as client:
        res = client.post("/api/search", json={
            "type": "TRAKE",
            "events": ["person enters", "person cooks food", "person eats"],
            "top_k": 2
        })
        assert res.status_code == 200
        data = res.json()
        assert "results" in data
        assert data["type"] == "TRAKE"


def test_visual_prf_algorithm():
    """Test Visual Pseudo-Relevance Feedback (Visual PRF) candidate rescoring."""
    from app.algorithms.visual_prf import apply_visual_pseudo_relevance_feedback

    class DummyStore:
        def reconstruct(self, v_id: int) -> np.ndarray:
            rng = np.random.RandomState(v_id)
            v = rng.randn(512).astype(np.float32)
            return v / np.linalg.norm(v)

    cands = [
        {"vector_id": 1, "video_id": "V1", "frame_id": 10, "score": 0.80},
        {"vector_id": 2, "video_id": "V1", "frame_id": 20, "score": 0.75},
        {"vector_id": 3, "video_id": "V2", "frame_id": 30, "score": 0.70},
    ]
    q_vec = np.ones(512, dtype=np.float32) / np.sqrt(512)
    store = DummyStore()

    updated = apply_visual_pseudo_relevance_feedback(
        cands, q_vec, store, top_m_visual=2, prf_weight=0.20
    )
    assert len(updated) == 3
    assert "score" in updated[0]
    assert all("prf_sim" in c for c in updated)


def test_temporal_consensus_algorithm():
    """Test Temporal Shot Consensus density boosting and isolated spike penalties."""
    from app.algorithms.temporal_consensus import apply_temporal_shot_consensus

    cands = [
        {"video_id": "V1", "timestamp": 10.0, "score": 0.60},
        {"video_id": "V1", "timestamp": 12.0, "score": 0.58},
        {"video_id": "V1", "timestamp": 14.0, "score": 0.55},
        {"video_id": "V2", "timestamp": 100.0, "score": 0.60},  # Isolated spike in V2
    ]

    updated = apply_temporal_shot_consensus(
        cands, window_seconds=15.0, consensus_boost_weight=0.15, isolated_penalty=0.04
    )
    assert len(updated) == 4
    # The cluster in V1 should be boosted
    v1_hits = [c for c in updated if c["video_id"] == "V1"]
    assert any("consensus_boost" in c for c in v1_hits)
    # The isolated hit in V2 should be discounted
    v2_hits = [c for c in updated if c["video_id"] == "V2"]
    assert v2_hits[0]["score"] < 0.60


def test_human_intent_nlu():
    """Test Vietnamese cultural slang, attire and compound action parsing."""
    from app.algorithms.human_intent_nlu import parse_human_intent

    # Cultural attire
    res_ninja = parse_human_intent("nữ ninja áo chống nắng đi xe lead")
    assert len(res_ninja.cultural_entities) >= 1
    assert "protection" in res_ninja.enriched_english_prompt.lower()

    # Compound action & negative constraint
    res_neg = parse_human_intent("người đi xe máy vừa đi vừa bấm điện thoại không đội mũ bảo hiểm")
    assert len(res_neg.compound_actions) >= 1
    assert res_neg.has_negative_constraint is True
    assert "helmet" in res_neg.negative_concept.lower()


def test_strict_paraphrase_engine():
    """Test strict morphological paraphrasing and anti-hallucination guard."""
    from app.algorithms.strict_paraphrase import generate_strict_paraphrases, BANNED_HALLUCINATIONS

    query = "a person walking in a room"
    paraphrases = generate_strict_paraphrases(query, max_variations=4)
    assert len(paraphrases) >= 2
    assert query in paraphrases

    # Verify no hallucinated substitutions
    for p in paraphrases:
        p_lower = p.lower()
        for banned in BANNED_HALLUCINATIONS:
            assert banned not in p_lower


def test_orthogonal_negative_projection():
    """Test Gram-Schmidt orthogonal subspace projection for negative constraints."""
    from app.algorithms.negative_projection import (
        extract_negative_constraint,
        project_orthogonal_negative_vector,
    )

    has_neg, pos_t, neg_t = extract_negative_constraint("a motorcyclist without a helmet")
    assert has_neg is True
    assert "helmet" in neg_t.lower()

    # Verify mathematical orthogonality reduction
    v_pos = np.array([1.0, 0.5, 0.0], dtype=np.float32)
    v_neg = np.array([0.0, 1.0, 0.0], dtype=np.float32)
    v_proj = project_orthogonal_negative_vector(v_pos, v_neg, alpha=1.0)
    
    # Dot product with negative vector must be approximately 0.0
    dot_neg = float(np.dot(v_proj, v_neg / np.linalg.norm(v_neg)))
    assert abs(dot_neg) < 1e-5


def test_symbolic_color_and_position_reasoner():
    """Test 0-token classical CV HSV color and centroid spatial position reasoners."""
    from app.algorithms.symbolic_reasoner import (
        classify_dominant_color_hsv,
        answer_symbolic_position_vqa,
        is_color_question,
        is_position_question,
    )

    assert is_color_question("What color is the car?") is True
    assert is_color_question("Áo của người đó màu gì?") is True
    assert is_position_question("Is the person on the left or right?") is True

    # Synthetic Red Crop
    red_crop = np.zeros((20, 20, 3), dtype=np.uint8)
    red_crop[:, :] = [240, 20, 20]  # Bright RGB Red
    assert classify_dominant_color_hsv(red_crop) == "red"

    # Synthetic Blue Crop
    blue_crop = np.zeros((20, 20, 3), dtype=np.uint8)
    blue_crop[:, :] = [20, 30, 240]  # Bright RGB Blue
    assert classify_dominant_color_hsv(blue_crop) == "blue"

    # Position Centroid on Left
    left_box = [[0.1, 0.1, 0.8, 0.3]]  # x_center = 0.2 (< 0.40)
    assert "left" in answer_symbolic_position_vqa(left_box)

    # Position Centroid on Right
    right_box = [[0.1, 0.7, 0.8, 0.9]]  # x_center = 0.8 (> 0.60)
    assert "right" in answer_symbolic_position_vqa(right_box)


def test_spatial_quadrant_roi_pooling():
    """Test 5-tile multi-scale spatial RoI slicing and trigger detection."""
    from app.algorithms.spatial_roi_pooling import (
        should_apply_spatial_roi_pooling,
        extract_spatial_quadrant_crops,
    )
    from PIL import Image

    assert should_apply_spatial_roi_pooling("a person wearing a watch and helmet") is True
    assert should_apply_spatial_roi_pooling("người đeo đồng hồ") is True
    assert should_apply_spatial_roi_pooling("a general landscape view") is False

    dummy_img = Image.new("RGB", (100, 100), color=(128, 128, 128))
    crops = extract_spatial_quadrant_crops(dummy_img)
    assert len(crops) == 5


def test_evaluation_engine_and_codabench_packager(tmp_path, monkeypatch):
    """Test mock contest evaluation harness and Codabench zip export."""
    from unittest.mock import MagicMock
    from app.features.submission.evaluation_engine import (
        evaluate_benchmark,
        package_codabench_submission,
    )

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "results": [
            {"video_id": "L22_V021", "frame_id": 166, "keyframe_id": 166, "timestamp": 10.0, "score": 0.95}
        ],
        "type": "KIS",
        "task_type": "KIS",
    }
    monkeypatch.setattr("requests.post", lambda *args, **kwargs: mock_resp)

    summary = evaluate_benchmark(
        ground_truth_path="data/mock_contest_ground_truth.json",
        base_url="http://localhost:8000",
        task_filter="KIS",
        top_k=5,
    )

    assert summary.total_queries == 10
    assert summary.top1_accuracy >= 0.0
    assert summary.p50_latency_ms >= 0.0
    assert len(summary.results) == 10

    # Test Codabench zip packaging
    zip_path = package_codabench_submission(summary, output_dir=tmp_path)
    assert zip_path.is_file()
    assert zip_path.suffix == ".zip"


def test_color_object_cooccurrence_extractor():
    """Test (Color, Object) extraction and constraint parser."""
    from app.algorithms.color_object_reranker import extract_color_object_constraints

    pairs = extract_color_object_constraints("xe buýt màu xanh lá cây trên đường")
    assert len(pairs) >= 1
    assert ("green", "bus") in pairs

    table_pairs = extract_color_object_constraints("wooden dining table in room")
    assert len(table_pairs) >= 1
    assert ("brown", "dining table") in table_pairs


def test_shot_level_temporal_smoothing_ema():
    """Test shot-level temporal neighborhood clustering and EMA aggregation."""
    from app.algorithms.temporal_smoothing import apply_temporal_smoothing

    candidates = [
        {"video_id": "V1", "frame_id": 100, "timestamp": 10.0, "score": 0.70},  # Strong anchor
        {"video_id": "V1", "frame_id": 105, "timestamp": 12.0, "score": 0.50},  # Weak neighbor — should be boosted
        {"video_id": "V2", "frame_id": 500, "timestamp": 50.0, "score": 0.52},  # Isolated frame
    ]

    smoothed = apply_temporal_smoothing(candidates, window_seconds=15.0, weight=0.30)
    v1_entry = next(c for c in smoothed if c["video_id"] == "V1" and c["frame_id"] == 105)
    assert v1_entry["temporal_boost"] > 0.0


def test_mediainfo_bm25_store():
    """Test MediaInfoStore indexing and BM25 term search."""
    from app.services.mediainfo_store import mediainfo_store

    count = mediainfo_store.build_index()
    assert count >= 0

    results = mediainfo_store.search_bm25("60 Giây HTV tin tức", top_k=5)
    # If media_info files exist, results should be found
    if count > 0:
        assert len(results) > 0
        assert results[0][1] > 0.0


def test_reciprocal_rank_fusion():
    """Test Cormack Reciprocal Rank Fusion rank merging."""
    from app.algorithms.reciprocal_rank_fusion import apply_reciprocal_rank_fusion

    visual_cands = [
        {"video_id": "V1", "frame_id": 10, "score": 0.80},
        {"video_id": "V2", "frame_id": 20, "score": 0.75},
        {"video_id": "V3", "frame_id": 30, "score": 0.70},
    ]

    media_ranks = [("V3", 10.5), ("V1", 5.2)]  # V3 has highest media relevance

    fused = apply_reciprocal_rank_fusion(
        visual_cands,
        mediainfo_video_ranks=media_ranks,
        k_constant=60,
    )

    assert len(fused) == 3
    assert "rrf_score" in fused[0]
    assert fused[0]["rank"] == 1


def test_multi_prompt_ensemble_variations():
    """Test multi-prompt 4-view generation and weight normalization."""
    from app.algorithms.multi_prompt_ensemble import (
        build_multi_prompt_variations,
        encode_multi_prompt_ensemble_vector,
    )

    variations = build_multi_prompt_variations("xe máy đi qua cầu")
    assert len(variations) == 4
    total_w = sum(w for _, w in variations)
    assert abs(total_w - 1.0) < 1e-4

    # Test mock encoder
    def mock_encoder(texts):
        return np.ones((len(texts), 512), dtype=np.float32)

    vec = encode_multi_prompt_ensemble_vector("traffic scene", mock_encoder)
    assert vec.shape == (512,)
    assert abs(np.linalg.norm(vec) - 1.0) < 1e-4


def test_vqa_ocr_token_resolver():
    """Test Tier 2 OCR token resolver for text and number questions."""
    from app.features.vqa.service import answer_vqa_question
    from app.services.ocr_store import ocr_store

    ocr_store._frame_ocr_entries[("V_TEST", 100)] = {"detected_text": "BẾN THÀNH 150"}
    top_kis = [{"video_id": "V_TEST", "keyframe_id": 100, "score": 0.90}]

    answers, t_ms = answer_vqa_question(top_kis, "What text is written on the sign?")
    assert len(answers) == 1
    assert "BẾN THÀNH 150" in answers[0]["answer"]
    assert answers[0]["source"] == "OCR_TOKEN_RESOLVER"
    assert t_ms < 100.0


def test_circuit_breaker_recovery_cycle():
    """Test CircuitBreaker state transitions and success recording."""
    from app.utils.circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitState
    cb = CircuitBreaker("test_cb", CircuitBreakerConfig(failure_threshold=2, recovery_timeout=0.05))
    res = cb.call(lambda x: x * 2, 21)
    assert res == 42
    assert cb.success_count == 1
    assert cb.state == CircuitState.CLOSED

    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    assert not cb.can_attempt()

    import time
    time.sleep(0.06)
    assert cb.can_attempt()
    assert cb.state == CircuitState.HALF_OPEN

    cb.call(lambda: "ok1")
    cb.call(lambda: "ok2")
    assert cb.state == CircuitState.CLOSED


def test_metadata_catalog_methods():
    """Test MetadataCatalog len and get methods."""
    from app.vector.metadata_catalog import MetadataCatalog
    from pathlib import Path
    cat = MetadataCatalog(Path("data/metadata.json"))
    assert len(cat) > 0
    assert cat.metadata_count == len(cat)
    row0 = cat.get(0)
    assert "video_id" in row0
    assert cat.metadata_for(0) == row0


def test_vqa_centroid_multiple_candidates():
    """Test that centroid position VQA returns all input candidates."""
    from app.features.vqa.service import answer_vqa_question
    from app.services.object_store import object_store

    top_kis = [
        {"video_id": "L01_V001", "keyframe_id": 1, "frame_id": 10, "score": 0.90},
        {"video_id": "L01_V001", "keyframe_id": 2, "frame_id": 20, "score": 0.85},
    ]
    def mock_get(v, k):
        return [{"label": "person", "score": 0.95, "box": [0.1, 0.1, 0.4, 0.4]}]
    orig = object_store.get_detections
    try:
        object_store.get_detections = mock_get
        answers, t_ms = answer_vqa_question(top_kis, "Where is the person located?")
        assert len(answers) == 2
        assert answers[0]["source"] == "SYMBOLIC_CENTROID_CV"
        assert answers[1]["source"] == "SYMBOLIC_CENTROID_CV"
    finally:
        object_store.get_detections = orig





