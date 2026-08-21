import json
from functools import lru_cache
from pathlib import Path

from app.core.config import settings


@lru_cache(maxsize=4096)
def _get_detections_cached(root_path: str, video_id: str, keyframe_id: int) -> tuple:
    root = Path(root_path)
    json_path = root / video_id / f"{keyframe_id:03d}.json"

    try:
        with json_path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except FileNotFoundError:
        return ()

    detections = []

    for score, label, box in zip(
        data.get("detection_scores", []),
        data.get("detection_class_entities", []),
        data.get("detection_boxes", []),
    ):
        detections.append({
            "label": str(label).strip().lower(),
            "score": float(score),
            "box": [float(value) for value in box],
        })

    return tuple(detections)


CLASS_ENTITY_ALIASES: dict[str, tuple[str, ...]] = {
    "person": ("person", "man", "woman", "human", "child", "boy", "girl", "people"),
    "car": ("car", "vehicle", "land vehicle", "automobile"),
    "bus": ("bus", "vehicle", "land vehicle"),
    "truck": ("truck", "vehicle", "land vehicle"),
    "motorbike": ("motorcycle", "motorbike", "vehicle", "land vehicle"),
    "bicycle": ("bicycle", "bike", "vehicle", "land vehicle"),
    "dog": ("dog", "mammal", "animal", "carnivore"),
    "cat": ("cat", "mammal", "animal", "carnivore", "feline"),
    "chair": ("chair", "furniture", "couch", "sofa"),
    "table": ("table", "desk", "coffee table", "furniture"),
    "bottle": ("bottle", "drink", "beverage", "water bottle"),
    "cup": ("cup", "mug", "drink", "coffee cup", "beverage"),
    "phone": ("mobile phone", "cell phone", "telephone", "phone", "electronics"),
    "building": ("building", "skyscraper", "tower", "house"),
    "tree": ("tree", "palm tree", "plant"),
}


SUBPART_ENTITY_CUES: dict[str, tuple[str, ...]] = {
    "person": (
        "clothing", "suit", "dress", "jeans", "pants", "shirt", "jacket", "footwear",
        "shoe", "human head", "human face", "human arm", "human body", "human hand",
        "human leg", "sunglasses", "glasses", "hat", "helmet", "cap", "coat", "boy", "girl"
    ),
    "car": ("wheel", "tire", "headlight", "license plate", "windshield", "car seat"),
    "bicycle": ("bicycle wheel", "tire", "handlebar"),
    "table": ("tableware", "plate", "bowl", "coffee cup", "fork", "knife", "spoon"),
}


class ObjectStore:
    def __init__(self, objects_dir: Path | str | None = None) -> None:
        self.objects_dir = Path(objects_dir or settings.OBJECT_ROOT)

    def get_detections(self, video_id: str, keyframe_id: int) -> list[dict]:
        raw = _get_detections_cached(str(self.objects_dir), video_id, keyframe_id)
        return list(raw)

    def clear_cache(self) -> None:
        """Clear the LRU cache to prevent memory leaks."""
        _get_detections_cached.cache_clear()  # type: ignore[attr-defined]

    def warm_up(self) -> None:
        """Prime the object store cache by reading sample bounding box files."""
        try:
            if not self.objects_dir.is_dir():
                return
            sample_dirs = [d for d in self.objects_dir.iterdir() if d.is_dir()][:2]
            for d in sample_dirs:
                sample_files = list(d.glob("*.json"))[:2]
                for f in sample_files:
                    try:
                        fid = int(f.stem)
                        self.get_detections(d.name, fid)
                    except ValueError:
                        pass
        except Exception:
            pass

    def find_by_class(
        self,
        video_id: str,
        keyframe_id: int,
        target_class: str,
        threshold: float = 0.5,
    ) -> list[dict]:
        normalized_target = target_class.strip().lower()
        aliases = CLASS_ENTITY_ALIASES.get(normalized_target, (normalized_target,))

        return [
            detection
            for detection in self.get_detections(video_id, keyframe_id)
            if any(alias in detection["label"] or detection["label"] in alias for alias in aliases)
            and detection["score"] >= threshold
        ]

    def count_with_uncertainty(
        self,
        video_id: str,
        keyframe_id: int,
        target_class: str,
        high_threshold: float = 0.55,
        mid_threshold: float = 0.35,
        low_threshold: float = 0.12,
        iou_threshold: float = 0.45,
    ) -> dict:
        """Evaluate counting certainty vs uncertainty across confidence thresholds and sub-part cues."""
        high_conf_boxes = self.count_by_class(
            video_id, keyframe_id, target_class, threshold=high_threshold, iou_threshold=iou_threshold
        )
        mid_conf_boxes = self.count_by_class(
            video_id, keyframe_id, target_class, threshold=mid_threshold, iou_threshold=iou_threshold
        )
        low_conf_boxes = self.count_by_class(
            video_id, keyframe_id, target_class, threshold=low_threshold, iou_threshold=iou_threshold
        )

        n_high = len(high_conf_boxes)
        n_mid = len(mid_conf_boxes)
        n_low = len(low_conf_boxes)
        volatility = abs(n_high - n_mid)
        mean_conf = (
            sum(b["score"] for b in high_conf_boxes) / n_high if n_high > 0 else 0.0
        )

        # Check sub-part cues for faint / occluded targets
        normalized_target = target_class.strip().lower()
        subpart_cues = SUBPART_ENTITY_CUES.get(normalized_target, ())
        all_detections = self.get_detections(video_id, keyframe_id)
        has_subpart_cues = any(
            any(cue in d["label"] or d["label"] in cue for cue in subpart_cues) and d["score"] >= low_threshold
            for d in all_detections
        )

        reasons: list[str] = []
        if n_mid >= 8:
            reasons.append("dense_crowd")
        if volatility >= 2:
            reasons.append("high_threshold_volatility")
        if n_high > 0 and mean_conf < 0.60:
            reasons.append("low_mean_confidence")
        if n_high == 0 and n_mid == 0 and (n_low > 0 or has_subpart_cues):
            reasons.append("faint_or_occluded_presence")

        uncertainty_level = "low"
        if len(reasons) == 1:
            uncertainty_level = "medium"
        elif len(reasons) >= 2:
            uncertainty_level = "high"

        should_use_vlm = uncertainty_level in ("medium", "high")

        return {
            "count": n_high if n_high > 0 else (n_mid if n_mid > 0 else n_low),
            "high_conf_count": n_high,
            "mid_conf_count": n_mid,
            "low_conf_count": n_low,
            "has_subpart_cues": has_subpart_cues,
            "mean_confidence": round(mean_conf, 3),
            "bboxes": high_conf_boxes or mid_conf_boxes or low_conf_boxes,
            "uncertainty_level": uncertainty_level,
            "should_use_vlm": should_use_vlm,
            "fallback_reasons": reasons,
        }

    def count_scale_aware(
        self,
        video_id: str,
        keyframe_id: int,
        target_class: str = "person",
        iou_threshold: float = 0.38,
        containment_threshold: float = 0.70,
    ) -> dict:
        """Count target objects using scale-aware dynamic thresholding and adaptive spatial NMS."""
        detections = self.get_detections(video_id, keyframe_id)
        if not detections:
            return {"count": 0, "bboxes": [], "status": "no_detections", "has_anchor": False}

        normalized_target = target_class.strip().lower()
        aliases = CLASS_ENTITY_ALIASES.get(normalized_target, (normalized_target,))
        anchor_cues = SUBPART_ENTITY_CUES.get(normalized_target, ())

        raw_candidates = []
        has_anchor = False

        for det in detections:
            score = float(det["score"])
            label = det["label"]
            box = det["box"]
            area = max(0.0, (box[2] - box[0])) * max(0.0, (box[3] - box[1]))

            # Check if this detection anchors the target class
            if any(cue in label or label in cue for cue in anchor_cues) and score >= 0.15:
                has_anchor = True

            # Scale-aware dynamic thresholding (tuned for clean precision)
            if area >= 0.05:
                min_score = 0.40
            elif area >= 0.005:
                min_score = 0.30
            else:
                min_score = 0.20  # Distant crowd figures

            if any(alias == label or alias in label for alias in aliases):
                if score >= min_score:
                    raw_candidates.append({
                        "score": score,
                        "box": box,
                        "area": area,
                        "label": label,
                    })

        # Noise suppression for isolated low-score false positives
        if len(raw_candidates) <= 2 and not has_anchor and all(c["score"] < 0.30 for c in raw_candidates):
            return {"count": 0, "bboxes": [], "status": "noise_suppressed", "has_anchor": False}

        # Sort candidates by score descending
        raw_candidates.sort(key=lambda x: x["score"], reverse=True)

        # Adaptive Spatial Containment & IoU NMS
        kept_boxes = []
        for cand in raw_candidates:
            box_a = cand["box"]
            area_a = cand["area"]
            overlap = False

            for kept in kept_boxes:
                box_b = kept["box"]
                area_b = kept["area"]

                ymin = max(box_a[0], box_b[0])
                xmin = max(box_a[1], box_b[1])
                ymax = min(box_a[2], box_b[2])
                xmax = min(box_a[3], box_b[3])

                inter_area = max(0.0, ymax - ymin) * max(0.0, xmax - xmin)
                if inter_area > 0:
                    union_area = area_a + area_b - inter_area
                    iou = inter_area / union_area if union_area > 0 else 0.0
                    containment = inter_area / min(area_a, area_b) if min(area_a, area_b) > 0 else 0.0

                    if iou >= iou_threshold or containment >= containment_threshold:
                        overlap = True
                        break

            if not overlap:
                from app.algorithms.local_cv_filters import estimate_box_posture
                cand["posture"] = estimate_box_posture(cand["box"])
                kept_boxes.append(cand)

        return {
            "count": len(kept_boxes),
            "bboxes": kept_boxes,
            "status": "scale_aware_rcnn",
            "has_anchor": has_anchor,
        }

    def count_with_confidence(
        self,
        video_id: str,
        keyframe_id: int,
        target_class: str,
        threshold: float = 0.4,
    ) -> dict:
        return self.count_with_uncertainty(video_id, keyframe_id, target_class, high_threshold=threshold, mid_threshold=0.3)

    @staticmethod
    def _iou(box_a: list[float], box_b: list[float]) -> float:
        # Boxes are [ymin, xmin, ymax, xmax].
        top = max(box_a[0], box_b[0])
        left = max(box_a[1], box_b[1])
        bottom = min(box_a[2], box_b[2])
        right = min(box_a[3], box_b[3])

        intersection_height = max(0.0, bottom - top)
        intersection_width = max(0.0, right - left)
        intersection = intersection_height * intersection_width

        area_a = max(0.0, box_a[2] - box_a[0]) * max(0.0, box_a[3] - box_a[1])
        area_b = max(0.0, box_b[2] - box_b[0]) * max(0.0, box_b[3] - box_b[1])

        union = area_a + area_b - intersection
        return intersection / union if union > 0 else 0.0

    def count_by_class(
        self,
        video_id: str,
        keyframe_id: int,
        target_class: str,
        threshold: float = 0.5,
        iou_threshold: float = 0.5,
    ) -> list[dict]:
        candidates = self.find_by_class(
            video_id,
            keyframe_id,
            target_class,
            threshold,
        )

        # Keep the highest-confidence box; discard overlapping duplicates.
        selected: list[dict] = []

        for detection in sorted(
            candidates,
            key=lambda detection: detection["score"],
            reverse=True,
        ):
            if all(
                self._iou(detection["box"], kept["box"]) < iou_threshold
                for kept in selected
            ):
                selected.append(detection)

        return selected


object_store = ObjectStore()
