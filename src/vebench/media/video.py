from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np


def video_stats(path: Path, *, sample_fps: float = 2.0) -> dict[str, Any]:
    import cv2

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {path}")

    fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    frame_step = max(1, int(round(fps / sample_fps)))
    sample_interval = frame_step / fps if fps > 0 else 0.5

    sampled = 0
    black = 0
    frozen_run = 0
    max_frozen_run = 0
    prev_small: np.ndarray | None = None
    luma_means: list[float] = []
    luma_vars: list[float] = []
    border_bar_scores: list[float] = []

    frame_idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if frame_idx % frame_step != 0:
            frame_idx += 1
            continue
        sampled += 1
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        mean = float(np.mean(gray))
        var = float(np.var(gray))
        luma_means.append(mean)
        luma_vars.append(var)
        if mean < 10.0 and var < 20.0:
            black += 1

        small = cv2.resize(gray, (96, 54), interpolation=cv2.INTER_AREA)
        if prev_small is not None:
            diff = float(np.mean(np.abs(small.astype(np.float32) - prev_small.astype(np.float32))))
            if diff < 1.2:
                frozen_run += 1
                max_frozen_run = max(max_frozen_run, frozen_run)
            else:
                frozen_run = 0
        prev_small = small

        h, w = gray.shape
        border = max(2, int(min(h, w) * 0.03))
        edge_pixels = np.concatenate(
            [
                gray[:border, :].reshape(-1),
                gray[-border:, :].reshape(-1),
                gray[:, :border].reshape(-1),
                gray[:, -border:].reshape(-1),
            ]
        )
        border_bar_scores.append(float(np.mean(edge_pixels < 8)))
        frame_idx += 1

    cap.release()
    if sampled == 0:
        return {
            "sampled_frames": 0,
            "black_frame_ratio": 1.0,
            "max_frozen_run_sec": 0.0,
            "mean_luma": 0.0,
            "mean_luma_var": 0.0,
            "border_black_fraction": 1.0,
            "duration_estimate_sec": 0.0,
        }

    return {
        "sampled_frames": sampled,
        "black_frame_ratio": black / sampled,
        "max_frozen_run_sec": max_frozen_run * sample_interval,
        "mean_luma": float(np.mean(luma_means)),
        "mean_luma_var": float(np.mean(luma_vars)),
        "border_black_fraction": float(np.mean(border_bar_scores)) if border_bar_scores else 0.0,
        "duration_estimate_sec": total_frames / fps if fps else 0.0,
    }


def video_integrity_score(stats: dict[str, Any]) -> float:
    if int(stats.get("sampled_frames", 0)) <= 0:
        return 0.0
    black_ratio = float(stats.get("black_frame_ratio", 1.0))
    frozen = float(stats.get("max_frozen_run_sec", 999.0))
    luma_var = float(stats.get("mean_luma_var", 0.0))
    black_score = max(0.0, 1.0 - max(0.0, black_ratio - 0.02) / 0.18)
    freeze_score = max(0.0, 1.0 - max(0.0, frozen - 0.75) / 4.0)
    texture_score = min(1.0, luma_var / 120.0)
    return float(0.45 * black_score + 0.35 * freeze_score + 0.20 * texture_score)
