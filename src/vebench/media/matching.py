from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .audio import read_audio_mono


@dataclass(frozen=True)
class MediaMatch:
    output_time: float
    source_time: float
    similarity: float


def match_video_timeline(
    *,
    output: Path,
    source: Path,
    output_fps: float = 1.0,
    source_fps: float = 1.0,
    threshold: float = 0.58,
) -> list[MediaMatch]:
    """Map sampled output frames to likely source times with crop-aware visual features."""
    try:
        import cv2
    except ModuleNotFoundError:
        return []

    source_entries = _sample_video_features(source, fps=source_fps, variants=True, cv2=cv2)
    output_entries = _sample_video_features(output, fps=output_fps, variants=False, cv2=cv2)
    if not source_entries or not output_entries:
        return []

    source_matrix = np.stack([entry["feature"] for entry in source_entries])
    matches: list[MediaMatch] = []
    for entry in output_entries:
        sims = source_matrix @ entry["feature"]
        best_idx = int(np.argmax(sims))
        similarity = float(sims[best_idx])
        if similarity >= threshold:
            matches.append(
                MediaMatch(
                    output_time=float(entry["time"]),
                    source_time=float(source_entries[best_idx]["time"]),
                    similarity=similarity,
                )
            )
    return matches


def match_audio_timeline(
    *,
    output: Path,
    source: Path,
    output_step_sec: float = 2.0,
    source_step_sec: float = 0.5,
    window_sec: float = 2.0,
    threshold: float = 0.35,
) -> list[MediaMatch]:
    """Map output audio windows to source audio windows with envelope fingerprints."""
    output_features = _audio_window_features(output, step_sec=output_step_sec, window_sec=window_sec)
    source_features = _audio_window_features(source, step_sec=source_step_sec, window_sec=window_sec)
    if not output_features or not source_features:
        return []

    source_matrix = np.stack([entry["feature"] for entry in source_features])
    matches: list[MediaMatch] = []
    for entry in output_features:
        sims = source_matrix @ entry["feature"]
        best_idx = int(np.argmax(sims))
        similarity = float(sims[best_idx])
        if similarity >= threshold:
            matches.append(
                MediaMatch(
                    output_time=float(entry["time"]),
                    source_time=float(source_features[best_idx]["time"]),
                    similarity=similarity,
                )
            )
    return matches


def matched_fraction(matches: list[MediaMatch], *, output_duration: float, sample_step_sec: float) -> float:
    expected = max(1, int(output_duration / max(sample_step_sec, 0.01)))
    return min(1.0, len(matches) / expected)


def seconds_in_intervals(matches: list[MediaMatch], intervals: list[tuple[float, float]], *, sample_step_sec: float) -> float:
    total = 0.0
    for match in matches:
        if any(start <= match.source_time <= end for start, end in intervals):
            total += sample_step_sec
    return total


def timeline_diversity(matches: list[MediaMatch], *, jump_threshold_sec: float = 3.0) -> int:
    if not matches:
        return 0
    spans = 1
    previous = matches[0].source_time
    for match in matches[1:]:
        if abs(match.source_time - previous) > jump_threshold_sec:
            spans += 1
        previous = match.source_time
    return spans


def timeline_monotonicity(matches: list[MediaMatch]) -> float:
    if len(matches) < 2:
        return 0.0 if not matches else 0.5
    violations = 0
    checked = 0
    previous = matches[0].source_time
    for match in matches[1:]:
        if match.source_time < previous - 1.0:
            violations += 1
        checked += 1
        previous = match.source_time
    return max(0.0, 1.0 - violations / max(1, checked))


def sync_residuals_ms(
    *,
    output: Path,
    clean_reference: Path,
    output_step_sec: float = 3.0,
    search_radius_sec: float = 1.0,
    window_sec: float = 1.5,
) -> list[float]:
    video_matches = match_video_timeline(
        output=output,
        source=clean_reference,
        output_fps=1.0 / output_step_sec,
        source_fps=2.0,
        threshold=0.55,
    )
    if not video_matches:
        return []

    try:
        output_audio = read_audio_mono(output, sample_rate=8000)
        reference_audio = read_audio_mono(clean_reference, sample_rate=8000)
    except Exception:  # noqa: BLE001
        return []

    residuals: list[float] = []
    for video_match in video_matches:
        out_chunk = _audio_center_chunk(output_audio, center_sec=video_match.output_time, sample_rate=8000, window_sec=window_sec)
        if out_chunk is None:
            continue
        out_chunk = _normalize_audio_chunk(out_chunk)
        best_corr = -1.0
        best_offset = 0.0
        for offset in np.arange(-search_radius_sec, search_radius_sec + 1e-9, 0.05):
            ref_chunk = _audio_center_chunk(
                reference_audio,
                center_sec=video_match.source_time + float(offset),
                sample_rate=8000,
                window_sec=window_sec,
            )
            if ref_chunk is None:
                continue
            ref_chunk = _normalize_audio_chunk(ref_chunk)
            corr = float(np.dot(out_chunk, ref_chunk) / max(1, out_chunk.size))
            if corr > best_corr:
                best_corr = corr
                best_offset = float(offset)
        if best_corr > 0.08:
            residuals.append(best_offset * 1000.0)
    return residuals


def _sample_video_features(path: Path, *, fps: float, variants: bool, cv2: Any) -> list[dict[str, Any]]:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return []

    native_fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    step = max(1, int(round(native_fps / max(fps, 0.01))))
    entries: list[dict[str, Any]] = []
    frame_idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if frame_idx % step != 0:
            frame_idx += 1
            continue
        time_sec = frame_idx / native_fps if native_fps > 0 else 0.0
        for crop in _video_crops(frame, variants=variants):
            feature = _frame_feature(crop, cv2=cv2)
            if feature is not None:
                entries.append({"time": time_sec, "feature": feature})
        frame_idx += 1
        if total_frames and frame_idx >= total_frames:
            break
    cap.release()
    return entries


def _video_crops(frame: np.ndarray, *, variants: bool) -> list[np.ndarray]:
    h, w = frame.shape[:2]
    if not variants:
        return [frame]
    crops = [frame]
    target_w = int(round(h * 9 / 16))
    if w > target_w > 16:
        for x in [0, (w - target_w) // 2, w - target_w]:
            crops.append(frame[:, x : x + target_w])
    target_w_square = min(w, h)
    if w > target_w_square:
        x = (w - target_w_square) // 2
        crops.append(frame[:, x : x + target_w_square])
    return crops


def _frame_feature(frame: np.ndarray, *, cv2: Any) -> np.ndarray | None:
    if frame.size == 0:
        return None
    h, w = frame.shape[:2]
    if h > 40:
        frame = frame[: int(h * 0.82), :]  # Downweight burned-in captions near the bottom.
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1, 2], None, [16, 4, 4], [0, 180, 0, 256, 0, 256]).reshape(-1)
    hist = hist.astype(np.float32)
    hist /= np.linalg.norm(hist) + 1e-9

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, (24, 24), interpolation=cv2.INTER_AREA).astype(np.float32).reshape(-1)
    gray -= float(np.mean(gray))
    gray /= np.linalg.norm(gray) + 1e-9
    feature = np.concatenate([0.65 * hist, 0.35 * gray])
    feature /= np.linalg.norm(feature) + 1e-9
    return feature.astype(np.float32)


def _audio_window_features(path: Path, *, step_sec: float, window_sec: float, sample_rate: int = 8000) -> list[dict[str, Any]]:
    try:
        samples = read_audio_mono(path, sample_rate=sample_rate)
    except Exception:  # noqa: BLE001
        return []
    window = int(window_sec * sample_rate)
    step = int(step_sec * sample_rate)
    if samples.size < window or window <= 0 or step <= 0:
        return []
    entries: list[dict[str, Any]] = []
    for start in range(0, samples.size - window + 1, step):
        chunk = samples[start : start + window]
        feature = _audio_feature(chunk, sample_rate=sample_rate)
        if feature is not None:
            entries.append({"time": (start + window / 2) / sample_rate, "feature": feature})
    return entries


def _audio_feature(chunk: np.ndarray, *, sample_rate: int) -> np.ndarray | None:
    if chunk.size == 0:
        return None
    chunk = chunk.astype(np.float32)
    chunk -= float(np.mean(chunk))
    if float(np.max(np.abs(chunk))) < 1e-5:
        return None

    frame = max(1, int(0.05 * sample_rate))
    usable = chunk[: (chunk.size // frame) * frame]
    if usable.size < frame:
        return None
    frames = usable.reshape((-1, frame))
    rms = np.sqrt(np.mean(np.square(frames), axis=1))
    rms = np.log1p(rms * 100.0)

    spectrum = np.abs(np.fft.rfft(chunk * np.hanning(chunk.size)))
    bands = np.array_split(np.log1p(spectrum), 32)
    band_energy = np.array([float(np.mean(band)) for band in bands], dtype=np.float32)
    feature = np.concatenate([rms.astype(np.float32), band_energy])
    feature -= float(np.mean(feature))
    feature /= np.linalg.norm(feature) + 1e-9
    return feature.astype(np.float32)


def _audio_center_chunk(samples: np.ndarray, *, center_sec: float, sample_rate: int, window_sec: float) -> np.ndarray | None:
    half = int(window_sec * sample_rate / 2)
    center = int(center_sec * sample_rate)
    start = center - half
    end = center + half
    if start < 0 or end > samples.size or end <= start:
        return None
    return samples[start:end].astype(np.float32)


def _normalize_audio_chunk(chunk: np.ndarray) -> np.ndarray:
    chunk = chunk.astype(np.float32)
    chunk = chunk - float(np.mean(chunk))
    norm = float(np.linalg.norm(chunk))
    if norm < 1e-8:
        return chunk
    return chunk / norm * np.sqrt(chunk.size)
