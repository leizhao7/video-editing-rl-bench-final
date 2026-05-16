from __future__ import annotations

import math
import subprocess
from pathlib import Path
from typing import Any

import numpy as np


def read_audio_mono(path: Path, *, sample_rate: int = 16000) -> np.ndarray:
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-f",
        "f32le",
        "pipe:1",
    ]
    result = subprocess.run(cmd, check=True, capture_output=True)
    return np.frombuffer(result.stdout, dtype=np.float32)


def audio_stats(path: Path, *, sample_rate: int = 16000) -> dict[str, Any]:
    samples = read_audio_mono(path, sample_rate=sample_rate)
    if samples.size == 0:
        return {
            "rms_dbfs": -120.0,
            "peak_dbfs": -120.0,
            "clipping_fraction": 0.0,
            "silence_ratio": 1.0,
            "max_silence_sec": 0.0,
        }

    peak = float(np.max(np.abs(samples)))
    rms = float(np.sqrt(np.mean(np.square(samples))))
    peak_dbfs = 20.0 * math.log10(max(peak, 1e-9))
    rms_dbfs = 20.0 * math.log10(max(rms, 1e-9))
    clipping_fraction = float(np.mean(np.abs(samples) >= 0.999))

    frame_len = max(1, int(sample_rate * 0.05))
    usable = samples[: (samples.size // frame_len) * frame_len]
    if usable.size == 0:
        silence_ratio = 1.0
        max_silence_sec = samples.size / sample_rate
    else:
        frames = usable.reshape((-1, frame_len))
        frame_rms = np.sqrt(np.mean(np.square(frames), axis=1))
        frame_db = 20.0 * np.log10(np.maximum(frame_rms, 1e-9))
        silence_threshold = min(-35.0, rms_dbfs - 18.0)
        silent = frame_db < silence_threshold
        silence_ratio = float(np.mean(silent))
        max_run = 0
        current = 0
        for is_silent in silent:
            if bool(is_silent):
                current += 1
                max_run = max(max_run, current)
            else:
                current = 0
        max_silence_sec = max_run * frame_len / sample_rate

    return {
        "rms_dbfs": rms_dbfs,
        "peak_dbfs": peak_dbfs,
        "clipping_fraction": clipping_fraction,
        "silence_ratio": silence_ratio,
        "max_silence_sec": max_silence_sec,
    }


def audio_quality_score(stats: dict[str, Any]) -> float:
    rms = float(stats.get("rms_dbfs", -120.0))
    peak = float(stats.get("peak_dbfs", -120.0))
    clipping = float(stats.get("clipping_fraction", 1.0))
    silence_ratio = float(stats.get("silence_ratio", 1.0))
    max_silence = float(stats.get("max_silence_sec", 999.0))

    if rms < -55.0 or clipping > 0.01:
        return 0.0

    if -26.0 <= rms <= -14.0:
        rms_score = 1.0
    elif rms < -26.0:
        rms_score = max(0.0, 1.0 - (-26.0 - rms) / 18.0)
    else:
        rms_score = max(0.0, 1.0 - (rms + 14.0) / 12.0)

    peak_score = 1.0 if peak <= -0.5 else max(0.0, 1.0 - (peak + 0.5) / 2.5)
    clip_score = max(0.0, 1.0 - clipping / 0.002)
    silence_score = max(0.0, 1.0 - max(0.0, silence_ratio - 0.12) / 0.28)
    max_silence_score = max(0.0, 1.0 - max(0.0, max_silence - 1.5) / 3.5)
    return float(0.35 * rms_score + 0.20 * peak_score + 0.20 * clip_score + 0.15 * silence_score + 0.10 * max_silence_score)
