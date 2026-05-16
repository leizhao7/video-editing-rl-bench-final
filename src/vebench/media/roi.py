from __future__ import annotations

from pathlib import Path
from typing import Any

from .matching import MediaMatch


def roi_visibility_score(
    *,
    source: Path,
    output: Path,
    matches: list[MediaMatch],
    roi_annotations: dict[str, Any],
    max_time_distance_sec: float = 1.0,
) -> tuple[float, dict[str, float]]:
    try:
        import cv2
        import numpy as np
    except ModuleNotFoundError:
        return 0.5, {"roi_visibility_checked": 0.0}

    annotations = roi_annotations.get("annotations", [])
    if not annotations or not matches:
        return 0.5, {"roi_visibility_checked": 0.0}

    visible = 0
    checked = 0
    scores: list[float] = []
    for annotation in annotations:
        source_time = float(annotation.get("time", -1.0))
        nearest = min(matches, key=lambda item: abs(item.source_time - source_time))
        if abs(nearest.source_time - source_time) > max_time_distance_sec:
            continue
        source_frame = _read_frame(source, source_time, cv2=cv2)
        output_frame = _read_frame(output, nearest.output_time, cv2=cv2)
        if source_frame is None or output_frame is None:
            continue

        required_labels = set(str(label).lower() for label in annotation.get("required_labels", []))
        objects = annotation.get("objects", [])
        for obj in objects:
            label = str(obj.get("label", "")).lower()
            if required_labels and label not in required_labels:
                continue
            bbox = obj.get("bbox")
            if not isinstance(bbox, list) or len(bbox) != 4:
                continue
            patch = _crop_bbox(source_frame, bbox)
            if patch is None:
                continue
            score = _best_template_score(patch, output_frame, cv2=cv2, np=np)
            scores.append(score)
            checked += 1
            if score >= 0.42:
                visible += 1

    if checked == 0:
        return 0.5, {"roi_visibility_checked": 0.0}
    return visible / checked, {
        "roi_visibility_checked": float(checked),
        "roi_template_mean_score": float(sum(scores) / len(scores)) if scores else 0.0,
    }


def _read_frame(path: Path, time_sec: float, *, cv2: Any) -> Any | None:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return None
    cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, time_sec) * 1000.0)
    ok, frame = cap.read()
    cap.release()
    return frame if ok else None


def _crop_bbox(frame: Any, bbox: list[Any]) -> Any | None:
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = [int(round(float(value))) for value in bbox]
    x1 = max(0, min(w - 1, x1))
    x2 = max(0, min(w, x2))
    y1 = max(0, min(h - 1, y1))
    y2 = max(0, min(h, y2))
    if x2 - x1 < 8 or y2 - y1 < 8:
        return None
    return frame[y1:y2, x1:x2]


def _best_template_score(patch: Any, frame: Any, *, cv2: Any, np: Any) -> float:
    patch_gray = cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY)
    frame_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    best = 0.0
    base_scale = frame.shape[0] / max(1, 720)
    for scale in [0.6, 0.8, 1.0, 1.25, 1.5, 1.75, 2.0, 2.35]:
        scaled_w = int(patch_gray.shape[1] * scale * base_scale)
        scaled_h = int(patch_gray.shape[0] * scale * base_scale)
        if scaled_w < 8 or scaled_h < 8 or scaled_w >= frame_gray.shape[1] or scaled_h >= frame_gray.shape[0]:
            continue
        resized = cv2.resize(patch_gray, (scaled_w, scaled_h), interpolation=cv2.INTER_AREA)
        if float(np.std(resized)) < 3.0:
            continue
        result = cv2.matchTemplate(frame_gray, resized, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, _ = cv2.minMaxLoc(result)
        best = max(best, float(max_val))
    return best
