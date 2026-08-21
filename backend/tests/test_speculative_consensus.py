"""Tests for Speculative Question Generation, Multi-Path Candidate Generation, and Consensus Judge."""

import pytest
from app.algorithms.speculative_qa import (
    CandidateAnswer,
    ConsensusJudge,
    SpeculativeQuestionGenerator,
    consensus_judge,
    speculative_question_generator,
)


def test_speculative_question_generator_probes():
    """Test generating multi-angle visual and semantic sub-questions from one intent."""
    query = "quán cà phê Highlands đông người"
    probes = speculative_question_generator.generate_probing_questions(query)

    assert len(probes) >= 4
    types = {p["type"] for p in probes}
    assert "primary_intent" in types
    assert "ocr_text_probe" in types
    assert "object_count_probe" in types
    assert "attribute_color_probe" in types


def test_consensus_judge_agreement_voting():
    """Test that cross-source agreement boosts confidence and picks the consensus winner."""
    candidates = [
        CandidateAnswer(
            text="Highlands Coffee",
            source="OCR_INVERTED_INDEX",
            confidence=0.90,
            rationale="Signboard OCR text",
        ),
        CandidateAnswer(
            text="Highlands Coffee shop",
            source="VLM_SPECULATIVE",
            confidence=0.88,
            rationale="VLM visual recognition",
        ),
        CandidateAnswer(
            text="Starbucks Coffee",
            source="VLM_HALLUCINATION",
            confidence=0.82,
            rationale="VLM single sample",
        ),
    ]

    winner, ranked = consensus_judge.evaluate_and_pick(candidates)

    assert winner.text in ("Highlands Coffee", "Highlands Coffee shop")
    assert winner.agreement_count >= 2
    assert winner.confidence > 0.90
    assert len(ranked) == 3


def test_consensus_judge_ocr_grounding():
    """Test that OCR text evidence elevates the grounded candidate."""
    candidates = [
        CandidateAnswer(
            text="Circle K",
            source="OCR_INVERTED_INDEX",
            confidence=0.85,
        ),
        CandidateAnswer(
            text="VinMart",
            source="VLM_SPECULATIVE",
            confidence=0.86,
        ),
    ]

    winner, ranked = consensus_judge.evaluate_and_pick(
        candidates,
        extracted_ocr_text="CIRCLE K 24/7 OPEN",
    )

    assert winner.text == "Circle K"
    assert winner.confidence >= 0.95
    assert "[OCR Grounded]" in winner.rationale


def test_consensus_judge_object_grounding():
    """Test that detected Faster R-CNN object classes elevate the grounded candidate."""
    candidates = [
        CandidateAnswer(
            text="person riding motorbike",
            source="VLM_SPECULATIVE",
            confidence=0.80,
        ),
        CandidateAnswer(
            text="dog running in park",
            source="VLM_SPECULATIVE",
            confidence=0.81,
        ),
    ]

    winner, ranked = consensus_judge.evaluate_and_pick(
        candidates,
        detected_objects=["person", "motorbike", "helmet"],
    )

    assert winner.text == "person riding motorbike"
    assert "[Object Grounded]" in winner.rationale


def test_consensus_judge_fallback_on_empty():
    """Test graceful fallback when no candidates are available."""
    winner, ranked = consensus_judge.evaluate_and_pick([])
    assert winner.text == "unknown"
    assert winner.source == "FALLBACK"
    assert len(ranked) == 1
