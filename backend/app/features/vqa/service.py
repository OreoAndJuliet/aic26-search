"""VQA orchestration: Faster R-CNN JSON first, VLM when uncertain."""

from __future__ import annotations

import logging
import re
import time

from app.core.config import settings
from app.services.object_store import object_store
from app.services.vqa_engine import vqa_engine
from app.utils.keyframes import keyframe_image_path
from app.utils.vqa_answer import build_vqa_prompt

logger = logging.getLogger(__name__)

COUNT_WORDS = ("how many", "number of", "count", "quantity", "bao nhiêu", "bao nhieu", "số lượng", "mấy", "may")

OBJECT_TARGET_PATTERNS: dict[str, tuple[str, ...]] = {
    "person": ("person", "people", "human", "man", "men", "woman", "women", "child", "children", "người", "nguoi"),
    "car": ("car", "cars", "automobile", "vehicle", "vehicles", "xe hơi", "xe hoi", "xe ô tô", "xe oto"),
    "bus": ("bus", "buses", "xe buýt", "xe buyt"),
    "truck": ("truck", "trucks", "xe tải", "xe tai"),
    "motorbike": ("motorbike", "motorcycle", "motorbikes", "motorcycles", "xe máy", "xe may"),
    "bicycle": ("bicycle", "bike", "bicycles", "bikes", "xe đạp", "xe dap"),
    "dog": ("dog", "dogs", "puppy", "chó", "cho"),
    "cat": ("cat", "cats", "kitten", "mèo", "meo"),
    "chair": ("chair", "chairs", "ghế", "ghe"),
    "table": ("table", "tables", "desk", "desks", "bàn", "ban"),
    "bottle": ("bottle", "bottles", "chai"),
    "cup": ("cup", "cups", "mug", "mugs", "cốc", "coc", "ly"),
    "phone": ("phone", "cellphone", "mobile", "điện thoại", "dien thoai"),
    "building": ("building", "buildings", "skyscraper", "tòa nhà", "toa nha"),
    "tree": ("tree", "trees", "cây", "cay"),
}


def parse_counting_target(question: str) -> tuple[bool, str]:
    """Identify if the question is a counting question and extract the target object class."""
    normalized = question.casefold()
    is_count = any(word in normalized for word in COUNT_WORDS)
    if not is_count:
        return False, ""

    for target_class, aliases in OBJECT_TARGET_PATTERNS.items():
        if any(re.search(rf"\b{re.escape(alias)}\b", normalized) for alias in aliases):
            return True, target_class

    return True, "person"  # default count target if ambiguous


def parse_existence_target(question: str) -> tuple[bool, str]:
    """Identify if the question is an existence question (Is there a... / Có...không)."""
    normalized = question.casefold()
    is_polar = any(normalized.startswith(prefix) for prefix in ("is there", "are there", "có ", "co ")) or "có " in normalized
    if not is_polar:
        return False, ""

    for target_class, aliases in OBJECT_TARGET_PATTERNS.items():
        if any(re.search(rf"\b{re.escape(alias)}\b", normalized) for alias in aliases):
            return True, target_class

    return False, ""

ADJECTIVE_ATTRIBUTE_PATTERNS: list[str] = [
    # Colors
    r"\b(?:red|blue|green|yellow|white|black|silver|pink|purple|orange|gray|grey|dark|bright|brown|golden)\b",
    r"\b(?:màu đỏ|màu xanh|màu vàng|màu trắng|màu đen|màu hồng|màu tím|màu cam|màu xám|màu nâu)\b",
    # Posture, state, actions
    r"\b(?:standing|sitting|walking|running|wearing|holding|carrying|riding|sleeping|eating|cooking|talking|swimming|flying|driving)\b",
    r"\b(?:đang đứng|đang ngồi|đang đi|đang chạy|mặc|đeo|cầm|mang|chở|đang ăn|đang nói|đang bơi|đang bay|đang lái)\b",
    # Status & condition
    r"\b(?:open|closed|empty|full|broken|working|damaged|lit|turned on|turned off)\b",
    r"\b(?:mở|đóng|trống|đầy|hỏng|bật|tắt)\b",
    # Materials, size, types
    r"\b(?:wooden|glass|plastic|metallic|leather|concrete|small|little|big|large|tall|short|young|old|police|electric)\b",
    r"\b(?:bằng gỗ|bằng kính|bằng nhựa|bằng kim loại|bằng da|nhỏ|bé|to|lớn|cao|thấp|trẻ|già|công an|cảnh sát)\b",
    # Prepositional / Relational modifiers
    r"\b(?:with|in front of|behind|near|next to|above|under|inside|outside)\b",
    r"\b(?:có mang|có đeo|ở phía trước|ở phía sau|bên cạnh|ở trên|ở dưới|trong|ngoài)\b",
]


def has_visual_attributes(question: str) -> bool:
    """Detect if the counting question contains adjectives, colors, actions, or attribute modifiers."""
    q_lower = question.lower()
    return any(re.search(pat, q_lower) for pat in ADJECTIVE_ATTRIBUTE_PATTERNS)


def is_person_count_question(question: str) -> bool:
    is_count, target = parse_counting_target(question)
    return is_count and target == "person"


def _answer_object_count(
    top_kis_results: list[dict], target_class: str, question: str
) -> tuple[list[dict], float]:
    if not top_kis_results:
        return [], 0.0

    from concurrent.futures import ThreadPoolExecutor

    vlm_started_at = time.perf_counter()
    strategy = settings.VQA_COUNTING_STRATEGY.lower().strip()
    has_attr = has_visual_attributes(question)

    def _process_count_candidate(result: dict) -> dict:
        candidate = result.copy()
        keyframe_id = int(candidate.get("keyframe_id", candidate.get("frame_id", 1)))

        # Run Scale-Aware & Density-Clustered Local Engine on Faster R-CNN JSON
        scale_res = object_store.count_scale_aware(
            candidate["video_id"],
            keyframe_id,
            target_class,
        )

        candidate["json_count"] = scale_res["count"]
        candidate["json_bboxes"] = scale_res["bboxes"]
        candidate["status"] = scale_res["status"]

        # If pure count (no adjectives/actions) and JSON index is healthy -> 0 tokens local speed (<1ms)
        if not has_attr and strategy != "vlm_only" and scale_res["status"] in ("scale_aware_rcnn", "noise_suppressed"):
            candidate["answer"] = str(scale_res["count"])
            candidate["source"] = "FASTER_RCNN_JSON"
            candidate["vlm_raw_log"] = ""
        else:
            # When adjectives, colors, postures, or actions are specified -> VLM visually verifies the attribute!
            image_path = keyframe_image_path(
                candidate["video_id"],
                keyframe_id,
                keyframes_dir=settings.KEYFRAMES_DIR,
            )
            vlm_raw_log = vqa_engine.answer_single_image(
                image_path,
                build_vqa_prompt(question),
            )
            candidate["answer"] = vlm_raw_log[:100]
            candidate["source"] = "DUAL_VERIFIED_VLM" if scale_res["count"] > 0 else "VLM_API"
            candidate["vlm_raw_log"] = vlm_raw_log

        return candidate

    max_workers = min(len(top_kis_results), settings.VQA_MAX_CONCURRENCY)
    if max_workers <= 1:
        processed_results = [_process_count_candidate(r) for r in top_kis_results]
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            processed_results = list(executor.map(_process_count_candidate, top_kis_results))

    vlm_time_ms = round((time.perf_counter() - vlm_started_at) * 1000, 2)
    return processed_results, vlm_time_ms



def answer_vqa_question(
    top_kis_results: list[dict],
    question: str,
) -> tuple[list[dict], float]:
    """Answer a VQA query using Speculative Multi-Candidate Generation and Consensus Judge ('Pick the 1 I Like')."""
    if not top_kis_results:
        return [], 0.0

    from app.algorithms.speculative_qa import CandidateAnswer, consensus_judge
    from app.services.ocr_store import ocr_store
    from app.algorithms.symbolic_reasoner import (
        answer_symbolic_color_vqa,
        answer_symbolic_position_vqa,
        is_color_question,
        is_position_question,
    )

    started_at = time.perf_counter()
    first_cand = top_kis_results[0]
    v_id = str(first_cand.get("video_id", ""))
    f_id = int(first_cand.get("frame_id", first_cand.get("keyframe_id", 1)))

    try:
        from app.services.kis_engine import kis_engine
        catalog = getattr(kis_engine.store, "_catalog", None)
        if catalog is None and hasattr(kis_engine.store, "_faiss"):
            catalog = getattr(kis_engine.store._faiss, "_catalog", None)
        meta_row = catalog.find_by_frame(v_id, f_id) if catalog and hasattr(catalog, "find_by_frame") else None
        kf_id = int(meta_row["keyframe_id"]) if meta_row and "keyframe_id" in meta_row else int(first_cand.get("keyframe_id", f_id))
    except Exception:
        kf_id = int(first_cand.get("keyframe_id", f_id))

    candidates_pool: list[CandidateAnswer] = []

    # 1. Faster R-CNN Counting / Existence
    is_count, target_class = parse_counting_target(question)
    is_exist, exist_target = parse_existence_target(question)

    detections = object_store.get_detections(v_id, kf_id) or object_store.get_detections(v_id, f_id)
    det_classes = [str(d.get("label", d.get("class", ""))) for d in (detections or []) if isinstance(d, dict)]
    ocr_text_parts = []
    if hasattr(ocr_store, "get_frame_ocr_text"):
        for cand in top_kis_results[:5]:
            c_vid = str(cand.get("video_id", ""))
            c_fid = int(cand.get("frame_id", cand.get("keyframe_id", 1)))
            c_kfid = int(cand.get("keyframe_id", c_fid))
            text = ocr_store.get_frame_ocr_text(c_vid, c_fid) or ocr_store.get_frame_ocr_text(c_vid, c_kfid)
            if text and text.strip():
                ocr_text_parts.append(text.strip())
    ocr_text = " | ".join(ocr_text_parts) if ocr_text_parts else ""

    if is_count and target_class:
        scale_res = object_store.count_scale_aware(v_id, kf_id, target_class)
        candidates_pool.append(
            CandidateAnswer(
                text=str(scale_res["count"]),
                source="FASTER_RCNN_SCALE",
                confidence=0.92 if scale_res["status"] == "scale_aware_rcnn" else 0.80,
                rationale=f"Scale-aware R-CNN detected {scale_res['count']} {target_class}(s)",
            )
        )

    if is_exist and exist_target:
        exist_matches = [c for c in det_classes if exist_target in c.lower()]
        candidates_pool.append(
            CandidateAnswer(
                text="yes" if exist_matches else "no",
                source="FASTER_RCNN_EXISTENCE",
                confidence=0.95 if exist_matches else 0.75,
                rationale=f"Object class '{exist_target}' detection match: {bool(exist_matches)}",
            )
        )

    # 2. Symbolic HSV Color Reasoner
    if is_color_question(question) and detections:
        img_path = keyframe_image_path(v_id, kf_id, keyframes_dir=settings.KEYFRAMES_DIR)
        color_ans = answer_symbolic_color_vqa(img_path, [d["box"] for d in detections[:2]])
        if color_ans and color_ans != "unknown":
            candidates_pool.append(
                CandidateAnswer(
                    text=color_ans,
                    source="SYMBOLIC_HSV_CV",
                    confidence=0.93,
                    rationale=f"HSV color histogram classified as '{color_ans}'",
                )
            )

    # 3. Symbolic Centroid Position Reasoner
    if is_position_question(question) and detections and not bool(re.search(r"\b(left\s+or\s+right|trái\s+hay\s+phải)\b", question, re.IGNORECASE)):
        pos_ans = answer_symbolic_position_vqa([d["box"] for d in detections[:1]])
        if pos_ans:
            candidates_pool.append(
                CandidateAnswer(
                    text=pos_ans,
                    source="SYMBOLIC_CENTROID_CV",
                    confidence=0.96,
                    rationale=f"Centroid spatial coordinate placed at '{pos_ans}'",
                )
            )

    # 4. Inverted OCR Store
    is_left_right = bool(re.search(r"\b(left\s+or\s+right|trái\s+hay\s+phải)\b", question, re.IGNORECASE))
    if ocr_text and ocr_text.strip() and not is_left_right:
        ocr_patterns = (
            "text", "number", "word", "name", "written", "sign", "license", "plate",
            "chữ", "chu", "số", "so", "biển", "bien", "bảng", "bang", "tên", "ten",
            "thương hiệu", "thuong hieu", "hãng", "hang", "quán", "quan", "cửa hàng",
            "cua hang", "brand", "store", "shop", "hiệu", "hieu"
        )
        from app.services.ocr_store import _strip_accents
        q_low = question.lower()
        q_no_acc = _strip_accents(q_low)
        if any(p in q_low or p in q_no_acc for p in ocr_patterns):
            candidates_pool.append(
                CandidateAnswer(
                    text=ocr_text.strip(),
                    source="OCR_TOKEN_RESOLVER",
                    confidence=0.85 if has_visual_attributes(question) else 0.96,
                    rationale=f"Extracted optical character recognition text '{ocr_text.strip()}'",
                )
            )

    # 5. Dual-Verified VLM Speculative Reasoning
    has_deterministic_fast_path = any(c.confidence >= 0.95 for c in candidates_pool)
    is_left_right = bool(re.search(r"\b(left\s+or\s+right|trái\s+hay\s+phải)\b", question, re.IGNORECASE))
    should_run_vlm = not has_deterministic_fast_path or is_left_right or (
        has_visual_attributes(question)
        and not any(c.source == "SYMBOLIC_CENTROID_CV" for c in candidates_pool)
    )

    if should_run_vlm or not candidates_pool:
        vlm_success = False
        for cand in top_kis_results[:5]:
            c_vid = str(cand.get("video_id", ""))
            c_fid = int(cand.get("frame_id", cand.get("keyframe_id", 1)))
            c_kfid = int(cand.get("keyframe_id", c_fid))
            try:
                image_path = keyframe_image_path(c_vid, c_kfid, keyframes_dir=settings.KEYFRAMES_DIR)
                if not image_path.exists():
                    image_path = keyframe_image_path(c_vid, c_fid, keyframes_dir=settings.KEYFRAMES_DIR)
                
                if image_path.exists():
                    vlm_prompt = build_vqa_prompt(question, ocr_context=ocr_text)
                    vlm_ans = vqa_engine.answer_single_image(image_path, vlm_prompt)
                    if vlm_ans and vlm_ans.strip():
                        candidates_pool.append(
                            CandidateAnswer(
                                text=vlm_ans.strip()[:100],
                                source="VLM_SPECULATIVE",
                                confidence=0.88,
                                rationale="Multimodal vision language model inference",
                            )
                        )
                    vlm_success = True
                    break
            except Exception as exc:
                logger.debug("VLM speculative inference skipped for cand %s: %s", c_vid, exc)
        
        if not vlm_success:
            logger.warning("VLM failed: No valid image found in top 5 KIS results")

    # 6. Consensus Judge ('Pick the 1 I Like')
    winner, ranked_alternatives = consensus_judge.evaluate_and_pick(
        candidates_pool,
        detected_objects=det_classes,
        extracted_ocr_text=ocr_text,
    )

    processed_results = []
    for r in top_kis_results:
        c = r.copy()
        c["answer"] = winner.text
        c["source"] = winner.source
        c["confidence"] = winner.confidence
        c["rationale"] = winner.rationale
        c["alternative_answers"] = [alt.to_dict() for alt in ranked_alternatives]
        processed_results.append(c)

    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
    return processed_results, elapsed_ms
