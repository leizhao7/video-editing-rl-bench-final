# Hackability Analysis

## Main hacking risks

- Remove too much interview content to eliminate dead air while losing semantic anchors.
- Generate generic, copied, badly timed, oversized, or visually occluding captions.
- Submit a clean-looking output that no longer matches the original speech.
- Mute, replace, or over-normalize audio to satisfy simple loudness or silence checks.
- Use unrelated footage, synthetic narration, heavy overlays, or non-source material.
- Write plausible edit notes without preserving the required explanation.

## Anti-hacking defenses

- Private semantic anchors and ASR/token matching check that key explanation content remains.
- Inserted-pause cleanup is paired with duration, spoken-word density, source-fidelity, and semantic-preservation checks to prevent over-trimming.
- Caption verification combines SRT validity, ASR token F1, timing-aware token F1, caption-speech consistency, and LLM text/layout checks.
- Source matching and non-degenerate audio/video checks penalize unrelated footage, blank video, still frames, and source replacement.
- Caption layout caps penalize oversized subtitles, subject occlusion, or unreadable burned-in text.
- Hard caps apply for fatal media failures, low semantic recall, weak pause removal, missing captions, low source match, weak caption layout, low LLM quality, and obvious non-source/synthetic content.

## Hackability classification

Semantic anchor preservation and source fidelity are hard-to-hack because they depend on private transcript anchors and source matching. Speech cleanup, audio normalization, and caption timing are hackable but bounded because over-deletion, muting, clipping, and desynchronization are measurable. Caption visual layout and publishability remain soft/vibes, so LLM judging is a minority signal paired with caps.
