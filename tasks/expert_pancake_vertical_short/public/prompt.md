# Task: Expert Pancake Tutorial Extraction

You are given `materials/source.mp4`, a landscape "50 People Try" pancake challenge video.

Create a 55-65 second vertical social tutorial that feels like a standalone pancake recipe short.

Find the expert/proficient pancake-making portion of the source and turn it into a clear
step-by-step tutorial. Do not build the edit around the novice blooper montage, failed attempts,
jokes, end cards, or unrelated banter.
Prefer a compact, coherent edit over a complex montage; use only as many cuts as needed to make the
tutorial clear.

Requirements:
- Export `submit/output.mp4` as portrait 9:16 H.264/AAC, preferably 1080x1920 or 720x1280.
- Use a true portrait crop/reframe. Do not fake vertical format by placing a landscape video inside
  black bars, blurred padding, or a decorative background.
- Keep pan, pancake, hands, spatula, and plated result visible in the vertical frame.
- Add short burned-in captions that break the method into clear sequential steps.
- Keep useful original cooking/speech audio, normalize loudness, and avoid clipping or silent padding.
- Do not add external footage, unrelated music, synthetic narration, generated visuals, or unrelated
  filler just to hit duration.
- Write `submit/edit_decision.json` with source ranges, output ranges, crop decisions, caption
  text/timing, audio adjustments, and measured self-checks.
- Write `submit/run_history.md` and `submit/agent_transcript.md` with your action log and
  observable work transcript/summary.
