from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def transcribe_video(
    video: Path,
    *,
    cache_path: Path | None = None,
    model_size: str | None = None,
    language: str | None = None,
) -> tuple[dict[str, Any] | None, list[str]]:
    notes: list[str] = []
    if cache_path and cache_path.exists():
        try:
            return json.loads(cache_path.read_text()), notes
        except json.JSONDecodeError:
            notes.append(f"ASR cache is invalid JSON: {cache_path}")

    try:
        from faster_whisper import WhisperModel
    except ModuleNotFoundError:
        return None, ["faster-whisper is not installed; ASR semantic checks skipped."]

    selected_model = model_size or os.environ.get("VEBENCH_ASR_MODEL", "tiny")
    compute_type = os.environ.get("VEBENCH_ASR_COMPUTE_TYPE", "int8")
    try:
        model = WhisperModel(selected_model, device="cpu", compute_type=compute_type)
        segments_iter, info = model.transcribe(
            str(video),
            language=language,
            vad_filter=True,
            word_timestamps=True,
            beam_size=1,
        )
        segments: list[dict[str, Any]] = []
        words: list[dict[str, Any]] = []
        for segment in segments_iter:
            segment_words = []
            for word in segment.words or []:
                item = {
                    "start": float(word.start),
                    "end": float(word.end),
                    "word": str(word.word).strip(),
                }
                words.append(item)
                segment_words.append(item)
            segments.append(
                {
                    "start": float(segment.start),
                    "end": float(segment.end),
                    "text": str(segment.text).strip(),
                    "words": segment_words,
                }
            )
        data = {
            "model": selected_model,
            "language": getattr(info, "language", language),
            "duration": float(getattr(info, "duration", 0.0) or 0.0),
            "segments": segments,
            "words": words,
            "text": " ".join(segment["text"] for segment in segments),
        }
        if cache_path:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        return data, notes
    except Exception as exc:  # noqa: BLE001
        notes.append(f"ASR failed with model {selected_model}: {exc}")
        return None, notes
