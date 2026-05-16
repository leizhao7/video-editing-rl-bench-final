from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ..fs import write_json
from ..media.captions import frame_base64
from ..verifiers.common import load_json_if_exists
from ..verifiers.llm_judge import openai_json_request


STEP_REQUIRED_LABELS = {
    "pan_butter": ["pan", "butter", "hand"],
    "batter_pour": ["pan", "batter", "hand"],
    "bubble_cue": ["pan", "pancake", "bubbles"],
    "flip": ["pancake", "spatula", "hand"],
    "plate_finish": ["pancake", "plate"],
}


def annotate_task_rois(*, repo: Path, task_id: str, model: str = "gpt-5.5", frames_per_step: int = 3) -> Path:
    if task_id != "expert_pancake_vertical_short":
        raise ValueError("ROI annotation is currently implemented for expert_pancake_vertical_short only.")
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for LLM ROI annotation.")

    source = repo / "tasks" / task_id / "public" / "materials" / "source.mp4"
    if not source.exists():
        raise FileNotFoundError(f"Missing source video: {source}")
    ground_truth = load_json_if_exists(repo / "tasks" / task_id / "private" / "ground_truth.json")
    if not ground_truth:
        raise FileNotFoundError(f"Missing private ground truth for {task_id}")

    annotations: list[dict[str, Any]] = []
    for step in ground_truth["required_steps"]:
        step_id = step["id"]
        start, end = [float(value) for value in step["interval"]]
        labels = STEP_REQUIRED_LABELS.get(step_id, ["pan", "pancake", "hand", "spatula", "plate"])
        times = _sample_times(start, end, frames_per_step)
        for time_sec in times:
            encoded = frame_base64(source, time_sec=time_sec)
            if not encoded:
                continue
            image_b64, width, height = encoded
            parsed = _annotate_frame(
                image_b64=image_b64,
                width=width,
                height=height,
                step_id=step_id,
                labels=labels,
                model=model,
                api_key=api_key,
            )
            annotations.append(
                {
                    "time": time_sec,
                    "step_id": step_id,
                    "required_labels": labels,
                    "frame_width": width,
                    "frame_height": height,
                    "objects": _clean_objects(parsed.get("objects", []), width=width, height=height),
                    "raw_rationale": parsed.get("rationale", ""),
                }
            )

    output = repo / "tasks" / task_id / "private" / "roi_keyframes.json"
    write_json(
        output,
        {
            "task_id": task_id,
            "annotator_model": model,
            "coordinate_space": "source_frame_pixels_xyxy",
            "annotations": annotations,
        },
    )
    return output


def _annotate_frame(
    *,
    image_b64: str,
    width: int,
    height: int,
    step_id: str,
    labels: list[str],
    model: str,
    api_key: str,
) -> dict[str, Any]:
    prompt = (
        f"Annotate this source video frame for benchmark ROI containment. "
        f"Frame size is {width}x{height}. The cooking step is {step_id}. "
        f"Find visible objects among these labels: {labels}. "
        "Return JSON with an objects array. Each object must have label, bbox, confidence. "
        "bbox must be [x1,y1,x2,y2] pixel coordinates in the original frame coordinate space. "
        "Only include objects that are clearly visible and important for the step."
    )
    return openai_json_request(
        model=model,
        system_text=(
            "You are a precise video-frame annotator. Return only JSON. "
            "Do not invent objects; mark only visible cooking ROIs."
        ),
        user_content=[
            {"type": "input_text", "text": prompt},
            {"type": "input_image", "image_url": f"data:image/jpeg;base64,{image_b64}"},
        ],
        api_key=api_key,
        max_output_tokens=900,
    )


def _sample_times(start: float, end: float, count: int) -> list[float]:
    if count <= 1:
        return [(start + end) / 2.0]
    margin = min(1.0, max(0.0, (end - start) * 0.1))
    low = start + margin
    high = end - margin
    if high <= low:
        low, high = start, end
    return [low + (high - low) * (idx + 0.5) / count for idx in range(count)]


def _clean_objects(objects: Any, *, width: int, height: int) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    if not isinstance(objects, list):
        return cleaned
    for obj in objects:
        if not isinstance(obj, dict):
            continue
        bbox = obj.get("bbox")
        if not isinstance(bbox, list) or len(bbox) != 4:
            continue
        x1, y1, x2, y2 = [float(value) for value in bbox]
        x1 = max(0.0, min(float(width), x1))
        x2 = max(0.0, min(float(width), x2))
        y1 = max(0.0, min(float(height), y1))
        y2 = max(0.0, min(float(height), y2))
        if x2 <= x1 or y2 <= y1:
            continue
        cleaned.append(
            {
                "label": str(obj.get("label", "")).lower(),
                "bbox": [x1, y1, x2, y2],
                "confidence": float(obj.get("confidence", 0.7)),
            }
        )
    return cleaned
