# Agent Transcript

## 1. Inspect workspace
- `ls /workspace` -> materials, submit, prompt.md, tools.md, source_metadata.json, output_specs.json, edit_decision.schema.json.
- Read tools.md (ffmpeg, ffprobe, python, numpy, librosa, etc., CPU-only).
- Read output_specs.json: portrait 9:16, duration 55-65s.

## 2. Probe source
- `ffprobe -show_streams materials/source.mp4` -> 1280x720, H.264 High @ 24000/1001, AAC 48kHz stereo, duration 292.96s.

## 3. Find the expert
- Sampled 1 frame / 3s into `work/frames/`, built 10x10 contact sheet `work/contact_sheet.jpg`. Observed Epicurious-style "50 People Try Pancakes": colorful aprons (novices) for most of the video, plus a chef in white coat with red ICE badge later.
- Built focused montages (`work/expert_sheet.jpg`, `work/edge_sheet.jpg`) to pin down the expert. Confirmed "Frank Proto / Chef Instructor / Institute of Culinary Education" appearing around 168s. Found the expert block runs roughly 165-264s.

## 4. Plan cuts
- Sampled 1 fps inside the expert block (`work/expertframes/ef_001..ef_100.jpg`). Built `work/expert_grid.jpg` and `work/expert_tall.jpg` to read each second.
- Picked 5 segments totaling ~60s:
  - 165-172 intro (chef at workbench, arms wide)
  - 175-185 butter going into hot pan (top-down)
  - 187-202 ladling batter (top-down + chef close-up)
  - 205-220 pancake cooking, hand on pan
  - 241-254 cooked pancake transferred to plate

## 5. Crop strategy
- 9:16 portrait from 1280x720 = 405x720.
- Center crop `438:0` for the wide intro; right-shifted crop `600:0` for the cooking/plating shots because the induction burner and plate sit to the right of frame center.
- Verified by sampling cropped frames (`work/check_c2.jpg`, `work/c4_check.jpg`) - pan, hands, pancake, plate stay inside the vertical crop.

## 6. Encode segments
- One `ffmpeg -ss -t` per segment with `crop=405:720:OFF:0,scale=1080:1920:flags=lanczos` -> `work/c1..c5.mp4` (libx264 crf 20, AAC 128k 48k stereo).
- Concatenated via `ffmpeg -f concat` -> `work/concat.mp4` (60.21s).

## 7. Burn captions and normalize
- Single pass with five paired drawtext entries (yellow "Step N" + white description, top-center, black border).
- Captions:
  1. 0.3-7s "Chef Frank Proto / Pancake Tutorial"
  2. 7.2-17s "Step 1 / Butter the hot pan"
  3. 17.2-32s "Step 2 / Ladle in the batter"
  4. 32.2-47s "Step 3 / Cook until golden"
  5. 47.2-60s "Step 4 / Plate and serve"
- Audio `loudnorm=I=-16:TP=-1.5:LRA=11`.
- Wrote `submit/output.mp4` H.264 yuv420p / AAC 48k stereo, +faststart.

## 8. Validate
- `ffprobe submit/output.mp4`: video h264 1080x1920, audio aac 48000 Hz stereo, duration 60.227s (within 55-65s target).
- Sampled output frames at t=3, 22, 50 -> captions readable, pan / chef / plate framed.
- librosa: max abs 0.86 (no clipping), RMS 0.111, silent fraction 0.035.
- Confirmed no novice/blooper or end-card content used; all source ranges sit inside the 165-254s expert window.
- True vertical crop, no decorative padding/blur.

## 9. Submission
- submit/output.mp4
- submit/edit_decision.json
- submit/run_history.md
- submit/agent_transcript.md
