from __future__ import annotations

import base64
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
