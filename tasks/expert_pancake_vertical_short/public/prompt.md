# Task: Expert Pancake Tutorial Extraction

You are given `materials/source.mp4`, a landscape "50 People Try" pancake challenge video.

Create a 55-65 second vertical social tutorial that feels like a standalone pancake recipe short.

Use the expert/proficient pancake-making sequence. Do not build the edit around the novice blooper
montage, failed attempts, jokes, end cards, or unrelated banter.

The final story must show these recipe steps in order:
1. grease the pan with butter,
2. pour or swirl the batter,
3. wait for bubbles as the doneness cue,
4. flip with a spatula,
5. plate and finish the pancake.

Requirements:
- Export `submit/output.mp4` as portrait 9:16 H.264/AAC, preferably 1080x1920 or 720x1280.
- Keep pan, pancake, hands, spatula, and plated result visible in the vertical frame.
- Add short burned-in captions for each recipe step.
- Keep useful original cooking/speech audio, normalize loudness, and avoid clipping or silent padding.
- Do not add external footage, unrelated music, synthetic narration, or generated visuals.
- Write `submit/edit_decision.json` with source ranges, output ranges, crop decisions, caption
  text/timing, audio adjustments, and measured self-checks.
- Write `submit/run_history.md` and `submit/agent_transcript.md` with your action log and
  observable work transcript/summary.
