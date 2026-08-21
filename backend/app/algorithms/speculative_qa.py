"""Speculative Multi-Query Expansion, Multi-Path Candidate Generation & Consensus Judge (AIC 2026).

Implements the elite competition pattern:
  1. Generate Multi-Perspective Probing Questions / Hypotheses from User Intent.
  2. Generate Best-of-N Candidate Answers across Local CV, Inverted OCR, and Speculative VLMs.
  3. Consensus Judge ('Pick the 1 I Like') selects the #1 verified winner and preserves ranked alternatives for human review.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class CandidateAnswer:
    text: str
    source: str
    confidence: float
    rationale: str = ""
    agreement_count: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "source": self.source,
            "confidence": round(self.confidence, 4),
            "rationale": self.rationale,
            "agreement_count": self.agreement_count,
        }


class SpeculativeQuestionGenerator:
    """Decomposes a user query/question into multi-angle visual and semantic sub-questions."""

    @staticmethod
    def generate_probing_questions(query: str, question: str | None = None) -> list[dict[str, str]]:
        q_text = (question or query).strip()
        probes: list[dict[str, str]] = []

        # 1. Primary Direct Intent
        probes.append({
            "type": "primary_intent",
            "question": q_text,
            "weight": "0.40",
        })

        # 2. Text / Sign / OCR Probe
        probes.append({
            "type": "ocr_text_probe",
            "question": f"What text, brand name, route number, or signboard is visible in: '{q_text}'?",
            "weight": "0.20",
        })

        # 3. Object / Counting Probe
        probes.append({
            "type": "object_count_probe",
            "question": f"What key objects, persons, or vehicles are present in: '{q_text}' and how many?",
            "weight": "0.20",
        })

        # 4. Visual Attribute & Color Probe
        probes.append({
            "type": "attribute_color_probe",
            "question": f"What colors, spatial positions, and actions characterize: '{q_text}'?",
            "weight": "0.20",
        })

        return probes


class ConsensusJudge:
    """Evaluates multi-path speculative candidate answers and picks the #1 consensus winner."""

    @staticmethod
    def _normalize_text(text: str) -> str:
        t = str(text).lower().strip()
        t = re.sub(r"[^\w\s]", "", t)
        return " ".join(t.split())

    @classmethod
    def evaluate_and_pick(
        cls,
        candidates: list[CandidateAnswer],
        *,
        detected_objects: list[str] | None = None,
        extracted_ocr_text: str | None = None,
    ) -> tuple[CandidateAnswer, list[CandidateAnswer]]:
        """Rank candidates, compute cross-source agreement, verify visual grounding, and select winner."""
        if not candidates:
            fallback = CandidateAnswer(
                text="unknown",
                source="FALLBACK",
                confidence=0.10,
                rationale="No candidate answers available",
            )
            return fallback, [fallback]

        # Calculate cross-source agreement bonus
        norm_answers = [cls._normalize_text(c.text) for c in candidates]
        for i, cand in enumerate(candidates):
            current_norm = norm_answers[i]
            if not current_norm:
                continue

            curr_tokens = set(current_norm.split())
            matches = 0
            for j, other_norm in enumerate(norm_answers):
                if i == j or not other_norm:
                    continue

                # Numbers / digits must match exactly
                if current_norm.isdigit() or other_norm.isdigit():
                    if current_norm == other_norm:
                        matches += 1
                elif len(current_norm) <= 3 or len(other_norm) <= 3:
                    if current_norm == other_norm:
                        matches += 1
                else:
                    other_tokens = set(other_norm.split())
                    # Exact match, token subset/superset, or significant word overlap
                    if current_norm == other_norm or curr_tokens.issubset(other_tokens) or other_tokens.issubset(curr_tokens):
                        matches += 1
                    elif len(curr_tokens & other_tokens) >= max(1, min(len(curr_tokens), len(other_tokens)) - 1):
                        matches += 1

            cand.agreement_count = 1 + matches
            if matches > 0:
                # Agreement bonus: +0.08 per agreeing peer
                cand.confidence = min(0.99, cand.confidence + (0.08 * matches))
                cand.rationale = f"Cross-source consensus validated by {matches} peer answer(s)"

        # Grounding check against OCR text
        if extracted_ocr_text:
            ocr_clean = cls._normalize_text(extracted_ocr_text)
            ocr_tokens = set(ocr_clean.split())
            for cand in candidates:
                cand_clean = cls._normalize_text(cand.text)
                if not cand_clean:
                    continue
                cand_toks = set(cand_clean.split())
                is_ocr_hit = False
                if cand_clean.isdigit():
                    is_ocr_hit = cand_clean in ocr_tokens or (re.search(rf"\b{re.escape(cand_clean)}\b", ocr_clean) is not None)
                elif len(cand_clean) <= 3:
                    is_ocr_hit = cand_clean in ocr_tokens
                else:
                    is_ocr_hit = cand_clean in ocr_clean or bool(cand_toks & ocr_tokens)
                if is_ocr_hit:
                    cand.confidence = min(1.0, cand.confidence + 0.15)
                    cand.rationale = f"{cand.rationale} [OCR Grounded]".strip()

        # Grounding check against Object Store detections
        if detected_objects:
            obj_set = {cls._normalize_text(o) for o in detected_objects if cls._normalize_text(o)}
            for cand in candidates:
                cand_clean = cls._normalize_text(cand.text)
                cand_toks = set(cand_clean.split())
                if any(o in cand_toks or any(t in o for t in cand_toks if len(t) >= 3) for o in obj_set):
                    cand.confidence = min(1.0, cand.confidence + 0.10)
                    cand.rationale = f"{cand.rationale} [Object Grounded]".strip()

        # Sort by confidence descending, then by agreement count descending
        ranked = sorted(candidates, key=lambda c: (c.confidence, c.agreement_count), reverse=True)
        winner = ranked[0]
        return winner, ranked


consensus_judge = ConsensusJudge()
speculative_question_generator = SpeculativeQuestionGenerator()
