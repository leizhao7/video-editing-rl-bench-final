from __future__ import annotations

import base64
import math
import tempfile
from pathlib import Path
from typing import Any


def burned_caption_visibility_score(video: Path, cue_times: list[float] | None = None) -> float:
    """Heuristic score for visible burned-in text in the lower caption-safe band."""
    try:
        import cv2
        import numpy as np
    except ModuleNotFoundError:
        return 0.5

    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        return 0.0
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration = frame_count / fps if fps > 0 else 0.0
    if cue_times:
        sample_times = [time for time in cue_times if 0 <= time <= duration]
    else:
        sample_times = [duration * frac for frac in [0.18, 0.32, 0.46, 0.60, 0.74, 0.88] if duration > 0]

    hits = 0
    checked = 0
    for time_sec in sample_times:
        cap.set(cv2.CAP_PROP_POS_MSEC, time_sec * 1000.0)
        ok, frame = cap.read()
        if not ok:
            continue
        checked += 1
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape
        band = gray[int(h * 0.55) : int(h * 0.92), int(w * 0.06) : int(w * 0.94)]
        if band.size == 0:
            continue
        edges = cv2.Canny(band, 60, 160)
        bright = band > 175
        dark = band < 70
        edge_density = float(np.mean(edges > 0))
        contrast_density = float(min(np.mean(bright), 0.08) + min(np.mean(dark), 0.08))
        components = cv2.connectedComponentsWithStats((edges > 0).astype("uint8"), 8)[2]
        text_like = 0
        for x, y, cw, ch, area in components[1:]:
            if 3 <= ch <= h * 0.12 and 3 <= cw <= w * 0.70 and 4 <= area <= 2000:
                text_like += 1
        if edge_density > 0.012 and contrast_density > 0.015 and text_like >= 5:
            hits += 1
    cap.release()
    if checked == 0:
        return 0.0
    return min(1.0, hits / checked)


def caption_layout_occlusion_score(
    video: Path,
    cue_times: list[float] | None = None,
    *,
    max_samples: int = 36,
) -> tuple[float, dict[str, float]]:
    """Estimate whether burned-in captions cover the face or main upper body.

    This is intentionally conservative: strong occlusion signals are useful hard-cap
    evidence, while weak/no subject detections keep the score bounded instead of
    pretending the layout is definitely safe.
    """
    try:
        import cv2
        import numpy as np
    except ModuleNotFoundError:
        return 0.5, {"caption_occlusion_checked_frames": 0.0}

    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        return 0.0, {"caption_occlusion_checked_frames": 0.0}

    fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration = frame_count / fps if fps > 0 else 0.0
    sample_times = _caption_sample_times(duration=duration, cue_times=cue_times, max_samples=max_samples)
    face_cascades = _load_face_cascades(cv2)

    checked = 0
    caption_detected = 0
    face_detected = 0
    subject_detected = 0
    face_occlusions: list[float] = []
    upper_occlusions: list[float] = []
    caption_area_ratios: list[float] = []
    lower_safe_hits = 0
    centered_hits = 0

    for time_sec in sample_times:
        cap.set(cv2.CAP_PROP_POS_MSEC, time_sec * 1000.0)
        ok, frame = cap.read()
        if not ok:
            continue
        checked += 1
        h, w = frame.shape[:2]
        caption_mask, caption_bbox, caption_confidence = _caption_visual_mask(frame, cv2=cv2, np=np)
        if caption_mask is None or caption_bbox is None or caption_confidence < 0.45:
            continue

        caption_detected += 1
        caption_area_ratios.append(float(np.mean(caption_mask > 0)))
        x1, y1, x2, y2 = caption_bbox
        center_x = ((x1 + x2) / 2.0) / max(1, w)
        center_y = ((y1 + y2) / 2.0) / max(1, h)
        if 0.58 <= center_y <= 0.92:
            lower_safe_hits += 1
        if 0.30 <= center_x <= 0.70:
            centered_hits += 1

        faces = _select_main_faces(_detect_face_boxes(frame, cv2=cv2, cascades=face_cascades), frame_height=h)
        upper_boxes = _upper_subject_boxes_from_faces(faces, width=w, height=h)
        if faces:
            face_detected += 1
            protected_faces = [_expand_box(face, width=w, height=h, scale_x=0.10, scale_y=0.06) for face in faces]
            face_occlusions.append(max(_mask_overlap_fraction(caption_mask, box, np=np) for box in protected_faces))
        if upper_boxes:
            subject_detected += 1
            upper_occlusions.append(max(_mask_overlap_fraction(caption_mask, box, np=np) for box in upper_boxes))

    cap.release()

    if checked == 0:
        return 0.0, {"caption_occlusion_checked_frames": 0.0}

    caption_ratio = caption_detected / checked
    face_ratio = face_detected / checked
    subject_ratio = subject_detected / checked
    max_face = max(face_occlusions) if face_occlusions else 0.0
    p95_face = _percentile(face_occlusions, 95)
    max_upper = max(upper_occlusions) if upper_occlusions else 0.0
    p95_upper = _percentile(upper_occlusions, 95)
    p95_area = _percentile(caption_area_ratios, 95)
    lower_safe_ratio = lower_safe_hits / max(1, caption_detected)
    centered_ratio = centered_hits / max(1, caption_detected)

    face_clear = _ramp_down(max_face, good=0.002, bad=0.020)
    upper_clear = _ramp_down(p95_upper, good=0.180, bad=0.450)
    area_score = _ramp_down(p95_area, good=0.220, bad=0.340)
    position_score = 0.65 * lower_safe_ratio + 0.35 * centered_ratio
    score = 0.45 * face_clear + 0.25 * upper_clear + 0.20 * area_score + 0.10 * position_score

    if caption_ratio < 0.30:
        score = min(score, 0.70)
    if face_ratio < 0.25 and subject_ratio < 0.25:
        score = min(score, 0.60)

    details = {
        "caption_occlusion_checked_frames": float(checked),
        "caption_detected_frame_ratio": float(caption_ratio),
        "face_detection_frame_ratio": float(face_ratio),
        "subject_detection_frame_ratio": float(subject_ratio),
        "max_face_occlusion": float(max_face),
        "p95_face_occlusion": float(p95_face),
        "max_upper_subject_occlusion": float(max_upper),
        "p95_upper_subject_occlusion": float(p95_upper),
        "p95_caption_area_ratio": float(p95_area),
        "caption_lower_safe_ratio": float(lower_safe_ratio),
        "caption_centered_ratio": float(centered_ratio),
        "r_no_face_or_subject_occlusion": float(max(0.0, min(1.0, score))),
    }
    return details["r_no_face_or_subject_occlusion"], details


def _caption_sample_times(*, duration: float, cue_times: list[float] | None, max_samples: int) -> list[float]:
    if duration <= 0:
        return []
    if cue_times:
        valid = sorted({round(float(time), 3) for time in cue_times if 0 <= float(time) <= duration})
        if len(valid) <= max_samples:
            return valid
        step = (len(valid) - 1) / max(1, max_samples - 1)
        return [valid[int(round(idx * step))] for idx in range(max_samples)]
    fractions = [0.14, 0.22, 0.30, 0.38, 0.46, 0.54, 0.62, 0.70, 0.78, 0.86]
    return [duration * fraction for fraction in fractions]


def _caption_visual_mask(frame: Any, *, cv2: Any, np: Any) -> tuple[Any | None, tuple[int, int, int, int] | None, float]:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    edges = cv2.Canny(gray, 60, 160)
    components = cv2.connectedComponentsWithStats((edges > 0).astype("uint8"), 8)[2]

    items: list[tuple[int, int, int, int, int, float, float]] = []
    for x, y, cw, ch, area in components[1:]:
        if ch < 3 or cw < 2:
            continue
        if ch > h * 0.14 or cw > w * 0.55:
            continue
        if area < 4 or area > 2500:
            continue
        aspect = cw / max(1, ch)
        if aspect > 18.0:
            continue
        crop = gray[y : y + ch, x : x + cw]
        if crop.size == 0:
            continue
        contrast = float(np.std(crop))
        extreme_fraction = float(np.mean((crop > 175) | (crop < 65)))
        if contrast < 12.0 or extreme_fraction < 0.08:
            continue
        items.append((int(x), int(y), int(cw), int(ch), int(area), contrast, extreme_fraction))

    if len(items) < 5:
        return None, None, 0.0

    groups = _group_text_components(items, frame_width=w, frame_height=h)
    if not groups:
        return None, None, 0.0

    groups = sorted(groups, key=lambda item: item[1], reverse=True)
    best_bbox, best_confidence = groups[0]
    if best_confidence < 0.45:
        return None, None, 0.0
    best_cy = (best_bbox[1] + best_bbox[3]) / 2.0
    selected = [
        (bbox, confidence)
        for bbox, confidence in groups[:4]
        if confidence >= 0.42 and abs(((bbox[1] + bbox[3]) / 2.0) - best_cy) <= h * 0.13
    ][:2]

    mask = np.zeros((h, w), dtype=np.uint8)
    union: list[tuple[int, int, int, int]] = []
    for bbox, confidence in selected:
        x1, y1, x2, y2 = bbox
        union.append(bbox)
        text_region = edges[y1:y2, x1:x2] > 0
        mask_view = mask[y1:y2, x1:x2]
        mask_view[text_region] = 255
        crop = gray[y1:y2, x1:x2]
        dark_fraction = float(np.mean(crop < 80)) if crop.size else 0.0
        area_ratio = ((x2 - x1) * (y2 - y1)) / max(1, h * w)
        if dark_fraction > 0.34 and area_ratio < 0.18 and confidence > 0.65:
            mask[y1:y2, x1:x2] = 255

    if not union:
        return None, None, 0.0

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 5))
    mask = cv2.dilate(mask, kernel, iterations=1)
    x1 = min(box[0] for box in union)
    y1 = min(box[1] for box in union)
    x2 = max(box[2] for box in union)
    y2 = max(box[3] for box in union)
    bbox = _clip_box((x1, y1, x2, y2), width=w, height=h)
    return mask, bbox, best_confidence


def _group_text_components(
    items: list[tuple[int, int, int, int, int, float, float]],
    *,
    frame_width: int,
    frame_height: int,
) -> list[tuple[tuple[int, int, int, int], float]]:
    rows: list[list[tuple[int, int, int, int, int, float, float]]] = []
    y_tolerance = max(16.0, frame_height * 0.045)
    for item in sorted(items, key=lambda value: value[1] + value[3] / 2.0):
        cy = item[1] + item[3] / 2.0
        for row in rows:
            row_cy = sum(value[1] + value[3] / 2.0 for value in row) / len(row)
            if abs(cy - row_cy) <= y_tolerance:
                row.append(item)
                break
        else:
            rows.append([item])

    groups: list[tuple[tuple[int, int, int, int], float]] = []
    for row in rows:
        if len(row) < 5:
            continue
        x1 = min(item[0] for item in row)
        y1 = min(item[1] for item in row)
        x2 = max(item[0] + item[2] for item in row)
        y2 = max(item[1] + item[3] for item in row)
        width = x2 - x1
        height = y2 - y1
        if width < frame_width * 0.10 or height > frame_height * 0.22:
            continue
        area_ratio = (width * height) / max(1, frame_width * frame_height)
        if area_ratio > 0.16:
            continue
        edge_area = sum(item[4] for item in row)
        density = edge_area / max(1.0, width * height)
        if density < 0.006 or density > 0.45:
            continue
        extreme = sum(item[6] for item in row) / len(row)
        if extreme < 0.10:
            continue
        span_score = min(1.0, width / max(1.0, frame_width * 0.45))
        count_score = min(1.0, len(row) / 14.0)
        density_score = min(1.0, density / 0.055)
        extreme_score = min(1.0, extreme / 0.35)
        lower_bonus = 1.0 if (y1 + y2) / (2.0 * frame_height) >= 0.50 else 0.72
        confidence = (
            0.34 * count_score
            + 0.28 * span_score
            + 0.18 * density_score
            + 0.12 * extreme_score
            + 0.08 * lower_bonus
        )
        pad_x = max(6, int(frame_width * 0.012))
        pad_y = max(4, int(frame_height * 0.010))
        groups.append((_clip_box((x1 - pad_x, y1 - pad_y, x2 + pad_x, y2 + pad_y), width=frame_width, height=frame_height), confidence))
    return groups


def _load_face_cascades(cv2: Any) -> list[Any]:
    cascades: list[Any] = []
    base = getattr(getattr(cv2, "data", None), "haarcascades", "")
    for name in ["haarcascade_frontalface_default.xml", "haarcascade_profileface.xml"]:
        path = Path(base) / name if base else Path(name)
        if path.exists():
            cascade = cv2.CascadeClassifier(str(path))
            if not cascade.empty():
                cascades.append(cascade)
    return cascades


def _detect_face_boxes(frame: Any, *, cv2: Any, cascades: list[Any]) -> list[tuple[int, int, int, int]]:
    if not cascades:
        return []
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    min_size = (max(32, int(w * 0.045)), max(32, int(h * 0.060)))
    boxes: list[tuple[int, int, int, int]] = []
    for cascade in cascades:
        detections = cascade.detectMultiScale(gray, scaleFactor=1.08, minNeighbors=4, minSize=min_size)
        for x, y, bw, bh in detections:
            if bw <= 0 or bh <= 0:
                continue
            aspect = bw / max(1, bh)
            if not 0.55 <= aspect <= 1.75:
                continue
            if bw > w * 0.65 or bh > h * 0.70:
                continue
            boxes.append(_clip_box((int(x), int(y), int(x + bw), int(y + bh)), width=w, height=h))
    return _dedupe_boxes(boxes)


def _upper_subject_boxes_from_faces(
    faces: list[tuple[int, int, int, int]],
    *,
    width: int,
    height: int,
) -> list[tuple[int, int, int, int]]:
    boxes: list[tuple[int, int, int, int]] = []
    for face in faces:
        x1, y1, x2, y2 = face
        fw = x2 - x1
        fh = y2 - y1
        cx = (x1 + x2) / 2.0
        top = y1 - 0.35 * fh
        bottom = y2 + 1.35 * fh
        left = cx - 1.45 * fw
        right = cx + 1.45 * fw
        boxes.append(_clip_box((int(left), int(top), int(right), int(bottom)), width=width, height=height))
    return boxes


def _select_main_faces(boxes: list[tuple[int, int, int, int]], *, frame_height: int) -> list[tuple[int, int, int, int]]:
    if not boxes:
        return []
    high_enough = [
        box
        for box in boxes
        if ((box[1] + box[3]) / 2.0) / max(1, frame_height) <= 0.62
    ]
    if not high_enough:
        return []
    ranked = sorted(high_enough, key=lambda item: (item[2] - item[0]) * (item[3] - item[1]), reverse=True)
    main_area = max(1, (ranked[0][2] - ranked[0][0]) * (ranked[0][3] - ranked[0][1]))
    return [
        box
        for box in ranked
        if ((box[2] - box[0]) * (box[3] - box[1])) >= main_area * 0.45
    ][:2]


def _mask_overlap_fraction(mask: Any, box: tuple[int, int, int, int], *, np: Any) -> float:
    x1, y1, x2, y2 = box
    if x2 <= x1 or y2 <= y1:
        return 0.0
    crop = mask[y1:y2, x1:x2] > 0
    return float(np.mean(crop)) if crop.size else 0.0


def _expand_box(
    box: tuple[int, int, int, int],
    *,
    width: int,
    height: int,
    scale_x: float,
    scale_y: float,
) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = box
    bw = x2 - x1
    bh = y2 - y1
    return _clip_box(
        (
            int(x1 - bw * scale_x),
            int(y1 - bh * scale_y),
            int(x2 + bw * scale_x),
            int(y2 + bh * scale_y),
        ),
        width=width,
        height=height,
    )


def _clip_box(box: tuple[int, int, int, int], *, width: int, height: int) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = box
    x1 = max(0, min(width - 1, int(x1)))
    y1 = max(0, min(height - 1, int(y1)))
    x2 = max(x1 + 1, min(width, int(x2)))
    y2 = max(y1 + 1, min(height, int(y2)))
    return x1, y1, x2, y2


def _dedupe_boxes(boxes: list[tuple[int, int, int, int]]) -> list[tuple[int, int, int, int]]:
    deduped: list[tuple[int, int, int, int]] = []
    for box in sorted(boxes, key=lambda item: (item[2] - item[0]) * (item[3] - item[1]), reverse=True):
        if all(_box_iou(box, kept) < 0.35 for kept in deduped):
            deduped.append(box)
    return deduped[:4]


def _box_iou(left: tuple[int, int, int, int], right: tuple[int, int, int, int]) -> float:
    x1 = max(left[0], right[0])
    y1 = max(left[1], right[1])
    x2 = min(left[2], right[2])
    y2 = min(left[3], right[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    left_area = max(0, left[2] - left[0]) * max(0, left[3] - left[1])
    right_area = max(0, right[2] - right[0]) * max(0, right[3] - right[1])
    denom = left_area + right_area - inter
    return inter / denom if denom > 0 else 0.0


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    rank = (len(ordered) - 1) * percentile / 100.0
    lower = int(math.floor(rank))
    upper = int(math.ceil(rank))
    if lower == upper:
        return float(ordered[lower])
    fraction = rank - lower
    return float(ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction)


def _ramp_down(value: float, *, good: float, bad: float) -> float:
    if value <= good:
        return 1.0
    if value >= bad:
        return 0.0
    return 1.0 - (value - good) / (bad - good)


def contact_sheet_base64(video: Path, *, frames: int = 8, width: int = 960) -> str | None:
    try:
        import cv2
        from PIL import Image, ImageDraw
    except ModuleNotFoundError:
        return None

    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        return None
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration = count / fps if fps > 0 else 0.0
    if duration <= 0:
        cap.release()
        return None

    images: list[Any] = []
    for idx in range(frames):
        time_sec = duration * (idx + 0.5) / frames
        cap.set(cv2.CAP_PROP_POS_MSEC, time_sec * 1000.0)
        ok, frame = cap.read()
        if not ok:
            continue
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        image = Image.fromarray(frame)
        image.thumbnail((width // 4, width // 4))
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, 72, 18), fill=(0, 0, 0))
        draw.text((4, 3), f"{time_sec:.1f}s", fill=(255, 255, 255))
        images.append(image.copy())
    cap.release()
    if not images:
        return None

    cols = min(4, len(images))
    rows = (len(images) + cols - 1) // cols
    cell_w = max(image.width for image in images)
    cell_h = max(image.height for image in images)
    sheet = Image.new("RGB", (cols * cell_w, rows * cell_h), (20, 20, 20))
    for idx, image in enumerate(images):
        x = (idx % cols) * cell_w
        y = (idx // cols) * cell_h
        sheet.paste(image, (x, y))

    with tempfile.NamedTemporaryFile(suffix=".jpg") as tmp:
        sheet.save(tmp.name, "JPEG", quality=80)
        return base64.b64encode(Path(tmp.name).read_bytes()).decode("ascii")


def frame_base64(video: Path, *, time_sec: float, max_width: int = 960) -> tuple[str, int, int] | None:
    try:
        import cv2
        from PIL import Image, ImageDraw
    except ModuleNotFoundError:
        return None

    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        return None
    cap.set(cv2.CAP_PROP_POS_MSEC, time_sec * 1000.0)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        return None

    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    original_h, original_w = frame.shape[:2]
    image = Image.fromarray(frame)
    if image.width > max_width:
        ratio = max_width / image.width
        image = image.resize((max_width, int(image.height * ratio)))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 92, 20), fill=(0, 0, 0))
    draw.text((4, 4), f"{time_sec:.2f}s", fill=(255, 255, 255))
    with tempfile.NamedTemporaryFile(suffix=".jpg") as tmp:
        image.save(tmp.name, "JPEG", quality=85)
        return base64.b64encode(Path(tmp.name).read_bytes()).decode("ascii"), original_w, original_h
