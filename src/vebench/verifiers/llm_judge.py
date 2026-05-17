from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from ..media.captions import contact_sheet_base64, frame_base64
from .common import clamp01, parse_srt


def maybe_run_llm_judge(
    *,
    task_id: str,
    workspace: Path,
    hard_scores: dict[str, float],
    edit_decision: dict[str, Any],
    model: str | None = None,
    enabled: bool = False,
) -> tuple[dict[str, float], list[str], dict[str, Any]]:
    if not enabled:
        return {"llm_judge_available": 0.0, "llm_overall": 0.0}, ["LLM judge disabled for this verify run."], {}
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return {"llm_judge_available": 0.0, "llm_overall": 0.0}, ["OPENAI_API_KEY is not set; skipped LLM judge."], {}

    selected_model = model or os.environ.get("VEBENCH_LLM_JUDGE_MODEL", "gpt-5.5")
    rubric = _task_rubric(task_id)
    evidence = _evidence_text(task_id=task_id, workspace=workspace, hard_scores=hard_scores, edit_decision=edit_decision, rubric=rubric)
    user_content: list[dict[str, Any]] = [{"type": "input_text", "text": evidence}]

    source_sheet = contact_sheet_base64(workspace / "materials" / "source.mp4")
    output_sheet = contact_sheet_base64(workspace / "submit" / "output.mp4")
    if source_sheet:
        user_content.append({"type": "input_text", "text": "Source contact sheet:"})
        user_content.append({"type": "input_image", "image_url": f"data:image/jpeg;base64,{source_sheet}"})
    if output_sheet:
        user_content.append({"type": "input_text", "text": "Output contact sheet:"})
        user_content.append({"type": "input_image", "image_url": f"data:image/jpeg;base64,{output_sheet}"})
    if task_id == "rough_interview_caption_cleanup":
        for idx, time_sec in enumerate(_caption_layout_sample_times(workspace), start=1):
            frame = frame_base64(workspace / "submit" / "output.mp4", time_sec=time_sec)
            if not frame:
                continue
            image_data, _width, _height = frame
            user_content.append({"type": "input_text", "text": f"Output caption layout sample {idx} at {time_sec:.2f}s:"})
            user_content.append({"type": "input_image", "image_url": f"data:image/jpeg;base64,{image_data}"})
    if task_id == "expert_pancake_vertical_short":
        for idx, sample in enumerate(_caption_transition_sample_times(workspace, edit_decision), start=1):
            for label, time_sec in sample:
                frame = frame_base64(workspace / "submit" / "output.mp4", time_sec=time_sec)
                if not frame:
                    continue
                image_data, _width, _height = frame
                user_content.append({"type": "input_text", "text": f"Pancake caption/action sample {idx} {label} at {time_sec:.2f}s:"})
                user_content.append({"type": "input_image", "image_url": f"data:image/jpeg;base64,{image_data}"})

    try:
        parsed = openai_json_request(
            model=selected_model,
            system_text=(
                "You are a strict video-editing benchmark judge. "
                "Score only the submitted output against the task rubric. "
                "Do not reward claims in edit_decision.json unless supported by hard metrics or visible evidence. "
                "Return compact JSON only."
            ),
            user_content=user_content,
            api_key=api_key,
            max_output_tokens=900,
        )
    except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        return {"llm_judge_available": 0.0, "llm_overall": 0.0}, [f"LLM judge failed: {exc}"], {}

    scores = {"llm_judge_available": 1.0}
    for key in rubric["keys"]:
        scores[f"llm_{key}"] = clamp01(float(parsed.get(key, 0.0)))
    scores["llm_overall"] = clamp01(sum(scores[f"llm_{key}"] * weight for key, weight in rubric["weights"].items()))
    if parsed.get("major_failures"):
        scores["llm_major_failure_count"] = float(len(parsed["major_failures"]))
    return scores, [f"LLM judge ran with model {selected_model}."], parsed


def openai_json_request(
    *,
    model: str,
    system_text: str,
    user_content: list[dict[str, Any]],
    api_key: str,
    max_output_tokens: int = 900,
) -> dict[str, Any]:
    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    api_style = os.environ.get("VEBENCH_LLM_API_STYLE", "").strip().lower()
    if api_style in {"chat", "chat_completions"} or "openrouter.ai" in base_url:
        data = _chat_completions_request(
            model=model,
            system_text=system_text,
            user_content=user_content,
            api_key=api_key,
            base_url=base_url,
            max_output_tokens=max_output_tokens,
        )
        text = _extract_chat_text(data)
        return _parse_json_object(text)

    payload = {
        "model": model,
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": system_text}]},
            {"role": "user", "content": user_content},
        ],
        "max_output_tokens": max_output_tokens,
    }
    data = _responses_request(payload, api_key=api_key, base_url=base_url)
    text = _extract_response_text(data)
    return _parse_json_object(text)


def _responses_request(payload: dict[str, Any], *, api_key: str, base_url: str) -> dict[str, Any]:
    request = urllib.request.Request(
        f"{base_url}/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def _chat_completions_request(
    *,
    model: str,
    system_text: str,
    user_content: list[dict[str, Any]],
    api_key: str,
    base_url: str,
    max_output_tokens: int,
) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_text},
            {"role": "user", "content": _chat_user_content(user_content)},
        ],
        "max_tokens": max_output_tokens,
    }
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": os.environ.get("OPENROUTER_SITE_URL", "https://github.com/leizhao7/video-editing-rl-bench"),
            "X-Title": os.environ.get("OPENROUTER_APP_NAME", "video-editing-rl-bench"),
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def _chat_user_content(user_content: list[dict[str, Any]]) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    for item in user_content:
        kind = item.get("type")
        if kind == "input_text":
            converted.append({"type": "text", "text": str(item.get("text", ""))})
        elif kind == "input_image":
            converted.append({"type": "image_url", "image_url": {"url": str(item.get("image_url", ""))}})
    return converted


def _extract_chat_text(data: dict[str, Any]) -> str:
    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            texts = [item.get("text", "") for item in content if isinstance(item, dict)]
            text = "\n".join(part for part in texts if part)
            if text:
                return text
    raise ValueError("Chat completion response did not contain message content")


def _extract_response_text(data: dict[str, Any]) -> str:
    if isinstance(data.get("output_text"), str):
        return data["output_text"]
    texts: list[str] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            if value.get("type") in {"output_text", "text"} and isinstance(value.get("text"), str):
                texts.append(value["text"])
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(data.get("output", []))
    if not texts:
        raise ValueError("OpenAI response did not contain output text")
    return "\n".join(texts)


def _parse_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            raise
        return json.loads(match.group(0))


def _task_rubric(task_id: str) -> dict[str, Any]:
    if task_id == "expert_pancake_vertical_short":
        return {
            "keys": [
                "step_caption_completeness",
                "caption_visual_alignment",
                "mobile_caption_readability",
                "tutorial_naturalness",
                "prompt_fit",
            ],
            "weights": {
                "step_caption_completeness": 0.30,
                "caption_visual_alignment": 0.25,
                "mobile_caption_readability": 0.20,
                "tutorial_naturalness": 0.15,
                "prompt_fit": 0.10,
            },
            "questions": [
                "Do the captions break the pancake method into the expected tutorial arc: grease/butter pan, pour or swirl batter, wait for bubbles, flip with spatula, and plate or finish?",
                "Around caption changes, does the visible action match the step named by the caption?",
                "Are captions appropriately sized and placed for a phone, without covering faces, hands, pan, pancake, spatula, or plated result?",
                "Does the edit flow naturally as a standalone tutorial rather than a blooper, joke, or unrelated montage?",
                "Does the output follow the prompt, including true vertical framing and no external footage/music/narration?",
            ],
        }
    if task_id == "piecewise_av_sync_repair":
        return {
            "keys": ["perceived_sync_watchability", "tutorial_continuity", "edit_polish"],
            "weights": {
                "perceived_sync_watchability": 0.40,
                "tutorial_continuity": 0.35,
                "edit_polish": 0.25,
            },
            "questions": [
                "Does the output look and sound naturally synchronized around claps, plosives, and gestures?",
                "Does it preserve the tutorial explanation in coherent order?",
                "Are pacing, cuts, audio level, and visual presentation publishable?",
            ],
        }
    if task_id == "rough_interview_caption_cleanup":
        return {
            "keys": [
                "semantic_completion",
                "meaning_order_preservation",
                "edit_naturalness",
                "caption_text_accuracy_sync",
                "caption_visual_layout",
                "publishability",
            ],
            "weights": {
                "semantic_completion": 0.30,
                "meaning_order_preservation": 0.20,
                "edit_naturalness": 0.20,
                "caption_text_accuracy_sync": 0.15,
                "caption_visual_layout": 0.10,
                "publishability": 0.05,
            },
            "questions": [
                "Does the clip preserve a coherent, self-contained interview idea?",
                "Does it keep the speaker's meaning and argument order intact without misleading reordering?",
                "Does the speech edit feel natural after pause/repeat cleanup?",
                "Do the captions match the spoken words closely enough and appear timed to speech?",
                "Are burned-in captions appropriately sized and placed, without covering the speaker's face or making the interview hard to watch?",
                "Is the final clip publishable as a polished educational interview excerpt?",
            ],
        }
    return {
        "keys": ["semantic_completion", "edit_naturalness", "caption_readability"],
        "weights": {
            "semantic_completion": 0.45,
            "edit_naturalness": 0.30,
            "caption_readability": 0.25,
        },
        "questions": [
            "Does the clip preserve a coherent, self-contained interview idea?",
            "Does the speech edit feel natural after pause/repeat cleanup?",
            "Are captions readable, accurate, and helpful?",
        ],
    }


def _evidence_text(
    *,
    task_id: str,
    workspace: Path,
    hard_scores: dict[str, float],
    edit_decision: dict[str, Any],
    rubric: dict[str, Any],
) -> str:
    prompt = (workspace / "prompt.md").read_text(errors="replace")[:3000] if (workspace / "prompt.md").exists() else ""
    srt_text = (workspace / "submit" / "captions.srt").read_text(errors="replace")[:4000] if (workspace / "submit" / "captions.srt").exists() else ""
    compact_scores = {key: round(value, 4) for key, value in hard_scores.items() if isinstance(value, (int, float))}
    edit_summary = json.dumps(edit_decision, ensure_ascii=False)[:5000]
    return (
        f"Task id: {task_id}\n\n"
        f"Task prompt excerpt:\n{prompt}\n\n"
        f"Hard verifier scores:\n{json.dumps(compact_scores, indent=2, sort_keys=True)}\n\n"
        f"Submission edit_decision excerpt:\n{edit_summary}\n\n"
        f"Submission captions.srt excerpt:\n{srt_text}\n\n"
        "Rubric questions:\n"
        + "\n".join(f"- {question}" for question in rubric["questions"])
        + "\n\nReturn exactly one JSON object with these numeric 0..1 keys: "
        + ", ".join(rubric["keys"])
        + '. Also include "major_failures" as an array of strings and "rationale" as one concise sentence.'
    )


def _caption_layout_sample_times(workspace: Path, *, max_frames: int = 5) -> list[float]:
    entries = parse_srt(workspace / "submit" / "captions.srt")
    if not entries:
        return []
    cue_times = sorted(
        {
            round((float(entry["start"]) + float(entry["end"])) / 2.0, 2)
            for entry in entries
            if float(entry.get("end", 0.0)) > float(entry.get("start", 0.0))
        }
    )
    if len(cue_times) <= max_frames:
        return cue_times
    positions = [0.08, 0.28, 0.50, 0.72, 0.92]
    selected = [cue_times[min(len(cue_times) - 1, max(0, round((len(cue_times) - 1) * position)))] for position in positions]
    deduped: list[float] = []
    for time_sec in selected:
        if all(abs(time_sec - kept) > 0.75 for kept in deduped):
            deduped.append(time_sec)
    return deduped[:max_frames]


def _caption_transition_sample_times(
    workspace: Path,
    edit_decision: dict[str, Any],
    *,
    max_cues: int = 4,
) -> list[list[tuple[str, float]]]:
    cue_times = _caption_layout_sample_times(workspace, max_frames=max_cues)
    if not cue_times:
        cue_times = _edit_decision_caption_times(edit_decision, max_cues=max_cues)
    output_path = workspace / "submit" / "output.mp4"
    duration = _probe_duration_seconds(output_path)
    samples: list[list[tuple[str, float]]] = []
    for time_sec in cue_times[:max_cues]:
        samples.append(
            [
                ("before", max(0.0, time_sec - 0.35)),
                ("at", max(0.0, time_sec)),
                ("after", min(duration, time_sec + 0.35) if duration > 0 else time_sec + 0.35),
            ]
        )
    return samples


def _edit_decision_caption_times(edit_decision: dict[str, Any], *, max_cues: int) -> list[float]:
    captions = edit_decision.get("captions")
    if not isinstance(captions, list):
        return []
    times: list[float] = []
    for item in captions:
        if not isinstance(item, dict):
            continue
        start = item.get("start", item.get("output_start"))
        end = item.get("end", item.get("output_end"))
        if isinstance(start, (int, float)) and isinstance(end, (int, float)) and end > start:
            times.append(round((float(start) + float(end)) / 2.0, 2))
        elif isinstance(start, (int, float)):
            times.append(round(float(start) + 0.5, 2))
    times = sorted(set(times))
    if len(times) <= max_cues:
        return times
    positions = [0.12, 0.38, 0.64, 0.88]
    return [times[min(len(times) - 1, max(0, round((len(times) - 1) * position)))] for position in positions[:max_cues]]


def _probe_duration_seconds(path: Path) -> float:
    if not path.exists():
        return 0.0
    try:
        import subprocess

        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return max(0.0, float(result.stdout.strip() or 0.0))
    except Exception:  # noqa: BLE001
        return 0.0
