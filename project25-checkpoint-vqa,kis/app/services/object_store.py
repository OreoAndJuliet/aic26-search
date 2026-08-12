import json
from functools import lru_cache
from pathlib import Path


class ObjectStore:
    def __init__(self, objects_dir: str = "data/objects") -> None:
        self.objects_dir = Path(objects_dir)

    @lru_cache(maxsize=5_000)
    def get_detections(self, video_id: str, keyframe_id: int) -> list[dict]:
        json_path = self.objects_dir / video_id / f"{keyframe_id:03d}.json"

        if not json_path.is_file():
            return []

        with json_path.open("r", encoding="utf-8") as file:
            data = json.load(file)

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

        return detections

    def find_by_class(
        self,
        video_id: str,
        keyframe_id: int,
        target_class: str,
        threshold: float = 0.5,
    ) -> list[dict]:
        normalized_target = target_class.strip().lower()

        return [
            detection
            for detection in self.get_detections(video_id, keyframe_id)
            if detection["label"] == normalized_target
            and detection["score"] >= threshold
        ]

    def count_with_confidence(
        self,
        video_id: str,
        keyframe_id: int,
        target_class: str,
        threshold: float = 0.4,
    ) -> dict:
        selected = self.count_by_class(
            video_id,
            keyframe_id,
            target_class,
            threshold=threshold,
        )

        stricter_count = len(
            self.count_by_class(
                video_id,
                keyframe_id,
                target_class,
                threshold=0.5,
            )
        )

        raw_candidates = self.find_by_class(
            video_id,
            keyframe_id,
            target_class,
            threshold=0.1,
        )

        reasons = []

        if len(selected) >= 4:
            reasons.append("crowd_count")

        if len(selected) != stricter_count:
            reasons.append("threshold_sensitive")

        if len(raw_candidates) - len(selected) >= 3:
            reasons.append("many_overlapping_or_low_confidence_boxes")

        return {
            "count": len(selected),
            "bboxes": selected,
            "should_use_vlm": bool(reasons),
            "fallback_reasons": reasons,
        }

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
