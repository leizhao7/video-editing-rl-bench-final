# Hackability Analysis

## Main hacking risks

- Use one global audio shift instead of repairing the piecewise A/V offsets.
- Delete difficult sections instead of repairing local sync, visual artifacts, duplicate inserts, or dead air.
- Pad the output with black frames, frozen frames, silence, or unrelated filler to satisfy duration.
- Mute, clip, or replace audio while appearing to pass basic loudness checks.
- Claim repairs in `edit_decision.json` without producing the corresponding media changes.

## Anti-hacking defenses

- A/V sync is checked with private clean-reference anchors using both global and segmented residual scores.
- Required-span coverage, source-time monotonicity, and duration gates penalize over-trimming.
- Black-boundary, visual-artifact, freeze/dead-air, duplicate-insert, silence, clipping, and audio-quality checks detect common padding and deletion hacks.
- Documentation is scored only as a small provenance signal and cannot rescue bad media.
- Hard caps apply for missing output, invalid media, bad duration, low content preservation, low task score, remaining major artifacts, duplicate cleanup failure, or severe audio cleanup failure.

## Hackability classification

The sync and content-preservation dimensions are hard-to-hack because they depend on private clean-reference timing and private required spans. Audio and visual cleanup are hackable but bounded because local heuristics can be optimized narrowly, but severe silence, clipping, artifacts, and over-trimming are detectable. LLM judging, when enabled, is soft/vibes and used only as a minority or diagnostic signal.
