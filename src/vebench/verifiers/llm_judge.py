from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from ..media.captions import contact_sheet_base64
from .common import clamp01


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

    payload = {
        "model": selected_model,
        "input": [
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "You are a strict video-editing benchmark judge. "
                            "Score only the submitted output against the task rubric. "
                            "Do not reward claims in edit_decision.json unless supported by hard metrics or visible evidence. "
                            "Return compact JSON only."
                        ),
                    }
                ],
            },
            {"role": "user", "content": user_content},
        ],
        "max_output_tokens": 900,
    }

    try:
        data = _responses_request(payload, api_key=api_key)
        text = _extract_response_text(data)
        parsed = _parse_json_object(text)
    except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        return {"llm_judge_available": 0.0, "llm_overall": 0.0}, [f"LLM judge failed: {exc}"], {}

    scores = {"llm_judge_available": 1.0}
    for key in rubric["keys"]:
        scores[f"llm_{key}"] = clamp01(float(parsed.get(key, 0.0)))
    scores["llm_overall"] = clamp01(sum(scores[f"llm_{key}"] * weight for key, weight in rubric["weights"].items()))
    if parsed.get("major_failures"):
        scores["llm_major_failure_count"] = float(len(parsed["major_failures"]))
    return scores, [f"LLM judge ran with model {selected_model}."], parsed


def _responses_request(payload: dict[str, Any], *, api_key: str) -> dict[str, Any]:
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


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
            "keys": ["tutorial_completeness", "continuity_pacing", "mobile_readability", "prompt_fit"],
            "weights": {
                "tutorial_completeness": 0.45,
                "continuity_pacing": 0.25,
                "mobile_readability": 0.20,
                "prompt_fit": 0.10,
            },
            "questions": [
                "Does the output clearly teach the five-step pancake process as a standalone short?",
                "Does it flow naturally without confusing jumps, repeated shots, or rushed audio?",
                "Are framing and captions usable on a phone?",
                "Does it feel like an expert tutorial rather than a comedy blooper montage?",
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
