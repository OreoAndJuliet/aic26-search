"""Isolated regression tests for language mismatch fixes.

These tests verify:
  1. Negative constraint extraction works for BOTH Vietnamese input and English translations.
  2. Object constraint parsing works for both Vietnamese and English numeric patterns.
  3. Metadata keyword scoring works across bilingual query+metadata pairs.
  4. The bilingual lookup_text approach provides superior coverage vs. English-only.
  5. top_k is not silently capped below MAX_TOP_K.

Run:  pytest tests/test_language_mismatch_fixes.py -v
"""

import pytest
import numpy as np


# ---------------------------------------------------------------------------
# 1. Negative Constraint — Bilingual Detection
# ---------------------------------------------------------------------------

class TestNegativeConstraintBilingual:
    """extract_negative_constraint must fire for BOTH Vietnamese and English inputs."""

    def test_vietnamese_khong_doi_mu(self):
        from app.algorithms.negative_projection import extract_negative_constraint
        has_neg, pos_text, neg_text = extract_negative_constraint(
            "người đi xe máy không đội mũ bảo hiểm"
        )
        assert has_neg is True, "Vietnamese 'không đội mũ bảo hiểm' must trigger negative constraint"
        assert "helmet" in neg_text.lower(), f"neg_text should mention helmet, got: {neg_text}"

    def test_english_without_helmet(self):
        from app.algorithms.negative_projection import extract_negative_constraint
        has_neg, pos_text, neg_text = extract_negative_constraint(
            "person riding motorbike without helmet"
        )
        assert has_neg is True, "English 'without helmet' must trigger negative constraint"
        assert "helmet" in neg_text.lower(), f"neg_text should mention helmet, got: {neg_text}"

    def test_english_without_a_helmet(self):
        """Google Translate often produces 'without a helmet'."""
        from app.algorithms.negative_projection import extract_negative_constraint
        has_neg, pos_text, neg_text = extract_negative_constraint(
            "a motorcyclist without a helmet on the road"
        )
        assert has_neg is True, "English 'without a helmet' must trigger negative constraint"

    def test_english_not_wearing_helmet(self):
        """Google Translate may produce 'not wearing a helmet'."""
        from app.algorithms.negative_projection import extract_negative_constraint
        has_neg, pos_text, neg_text = extract_negative_constraint(
            "motorcyclist not wearing a helmet"
        )
        assert has_neg is True, "English 'not wearing a helmet' must trigger negative constraint"

    def test_vietnamese_khong_mac_ao(self):
        from app.algorithms.negative_projection import extract_negative_constraint
        has_neg, pos_text, neg_text = extract_negative_constraint(
            "người không mặc áo"
        )
        assert has_neg is True

    def test_english_without_shirt(self):
        from app.algorithms.negative_projection import extract_negative_constraint
        has_neg, pos_text, neg_text = extract_negative_constraint(
            "person without shirt"
        )
        assert has_neg is True, "English 'without shirt' must trigger negative constraint"

    def test_vietnamese_khong_mang_khau_trang(self):
        from app.algorithms.negative_projection import extract_negative_constraint
        has_neg, _, neg_text = extract_negative_constraint(
            "người không đeo khẩu trang"
        )
        assert has_neg is True
        assert "mask" in neg_text.lower()

    def test_english_without_mask(self):
        from app.algorithms.negative_projection import extract_negative_constraint
        has_neg, _, neg_text = extract_negative_constraint(
            "a person without mask in public"
        )
        assert has_neg is True

    def test_no_false_positive_normal_query(self):
        from app.algorithms.negative_projection import extract_negative_constraint
        has_neg, _, _ = extract_negative_constraint(
            "a woman walking near a tall building"
        )
        assert has_neg is False

    def test_no_false_positive_khong_gian(self):
        """'không gian' means 'space/atmosphere', not a negation."""
        from app.algorithms.negative_projection import extract_negative_constraint
        has_neg, _, _ = extract_negative_constraint(
            "không gian quán cà phê đẹp"
        )
        assert has_neg is False


# ---------------------------------------------------------------------------
# 2. Object Constraint Parsing — Bilingual
# ---------------------------------------------------------------------------

class TestObjectConstraintBilingual:
    """parse_object_constraints must handle both languages in a combined string."""

    def test_english_two_cars(self):
        from app.algorithms.kis_postprocess import parse_object_constraints
        constraints = parse_object_constraints("two cars on the road")
        targets = [c.target_class for c in constraints]
        assert "car" in targets, f"Should detect 'car' from English, got {targets}"

    def test_english_3_people(self):
        from app.algorithms.kis_postprocess import parse_object_constraints
        constraints = parse_object_constraints("3 people crossing the street")
        found = [c for c in constraints if c.target_class == "person"]
        assert len(found) > 0, "Should detect person constraint from '3 people'"
        assert found[0].min_count == 3

    def test_vietnamese_hai_xe_may(self):
        from app.algorithms.kis_postprocess import parse_object_constraints
        constraints = parse_object_constraints("hai xe máy trên đường")
        targets = [c.target_class for c in constraints]
        assert "motorbike" in targets, f"Should detect motorbike from Vietnamese, got {targets}"

    def test_bilingual_combined(self):
        """The bilingual lookup_text should catch constraints from both languages."""
        from app.algorithms.kis_postprocess import parse_object_constraints
        # Simulating lookup_text = raw_query + " " + translated_text
        combined = "hai xe máy trên đường two motorcycles on the road"
        constraints = parse_object_constraints(combined)
        targets = [c.target_class for c in constraints]
        assert "motorbike" in targets, f"Combined bilingual text should catch motorbike, got {targets}"

    def test_vietnamese_ba_nguoi(self):
        from app.algorithms.kis_postprocess import parse_object_constraints
        constraints = parse_object_constraints("ba người đi bộ qua đường")
        found = [c for c in constraints if c.target_class == "person"]
        assert len(found) > 0, "Should detect person constraint from 'ba người'"
        assert found[0].min_count == 3


# ---------------------------------------------------------------------------
# 3. Metadata Keyword Scoring — Cross-Language
# ---------------------------------------------------------------------------

class TestMetadataKeywordScoreBilingual:
    """keyword_score must match Vietnamese metadata fields against bilingual queries."""

    def _make_store_with_data(self, video_id: str, info: dict):
        """Create a MediaInfoStore patched to return the given info."""
        from app.services.media_info_store import MediaInfoStore
        store = MediaInfoStore.__new__(MediaInfoStore)
        store.root = None
        store._test_data = {video_id: info}
        original_get = store.get
        store.get = lambda vid: store._test_data.get(vid)
        return store

    def test_english_only_misses_vietnamese_title(self):
        """English-only query will NOT match Vietnamese title (demonstrating the flaw)."""
        store = self._make_store_with_data("L01_V001", {
            "title": "Cảnh sát giao thông xử phạt trên đường Nguyễn Huệ",
            "description": "Video quay cảnh CSGT làm việc trên đường",
        })
        score_en = store.keyword_score("L01_V001", "traffic police on the road")
        # English terms won't match Vietnamese title/description
        assert score_en == 0.0, f"English-only should score 0 against Vietnamese metadata, got {score_en}"

    def test_bilingual_lookup_matches(self):
        """Bilingual lookup_text includes Vietnamese original, so it WILL match Vietnamese metadata."""
        store = self._make_store_with_data("L01_V001", {
            "title": "Cảnh sát giao thông xử phạt trên đường Nguyễn Huệ",
            "description": "Video quay cảnh CSGT làm việc trên đường",
        })
        bilingual = "cảnh sát giao thông trên đường traffic police on the road"
        score_bi = store.keyword_score("L01_V001", bilingual)
        assert score_bi > 0.0, f"Bilingual lookup should score > 0 against Vietnamese metadata, got {score_bi}"

    def test_exact_vietnamese_query(self):
        store = self._make_store_with_data("L05_V003", {
            "title": "Xe buýt số 86 chạy trên đường Lê Lợi",
            "description": "",
        })
        score = store.keyword_score("L05_V003", "xe buýt đường Lê Lợi")
        assert score > 0.0, f"Vietnamese query should match Vietnamese title, got {score}"


# ---------------------------------------------------------------------------
# 4. Hybrid Ranking Metadata Overlap — Cross-Language
# ---------------------------------------------------------------------------

class TestHybridMetadataOverlapBilingual:
    """metadata_overlap_score must benefit from bilingual lookup."""

    def test_english_only_zero_overlap(self):
        from app.algorithms.hybrid_ranking import _tokenize, _result_text
        query_tokens = _tokenize("traffic police officer")
        result = {"media_title": "Cảnh sát giao thông", "video_id": "L01_V001"}
        result_tokens = _tokenize(_result_text(result))
        overlap = query_tokens & result_tokens
        assert len(overlap) == 0, f"English-only should have 0 overlap with Vietnamese metadata, got {overlap}"

    def test_bilingual_has_overlap(self):
        from app.algorithms.hybrid_ranking import _tokenize, _result_text
        bilingual_query = "cảnh sát giao thông traffic police officer"
        query_tokens = _tokenize(bilingual_query)
        result = {"media_title": "Cảnh sát giao thông", "video_id": "L01_V001"}
        result_tokens = _tokenize(_result_text(result))
        overlap = query_tokens & result_tokens
        assert len(overlap) > 0, f"Bilingual query should overlap with Vietnamese metadata, got {overlap}"


# ---------------------------------------------------------------------------
# 5. Determine Adaptive Candidate Pool — Sanity Check
# ---------------------------------------------------------------------------

class TestAdaptiveCandidatePool:
    """Candidate pool must always be >= requested top_k."""

    def test_pool_exceeds_top_k_100(self):
        from app.features.search.retrieval import determine_adaptive_candidate_pool_size
        pool = determine_adaptive_candidate_pool_size("simple query", 100)
        assert pool >= 100, f"Pool {pool} must be >= top_k 100"
        assert pool >= 500, f"Pool {pool} should be at least 500 for proper reranking"

    def test_pool_for_complex_query(self):
        from app.features.search.retrieval import determine_adaptive_candidate_pool_size
        pool = determine_adaptive_candidate_pool_size(
            "a woman wearing red jacket walking near wooden bridge at sunset", 100
        )
        assert pool >= 1000, f"Complex query pool {pool} should be >= 1000"

    def test_pool_for_short_query(self):
        from app.features.search.retrieval import determine_adaptive_candidate_pool_size
        pool = determine_adaptive_candidate_pool_size("motorbike", 100)
        assert pool >= 500, f"Short query pool {pool} should be >= 500"
