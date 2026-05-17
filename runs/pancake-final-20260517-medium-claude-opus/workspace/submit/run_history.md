# Run History

## Detection
- Probed `materials/source.mp4` with ffprobe: 1280x720, H.264/AAC, ~293s, 24000/1001 fps.
- Sampled 1 frame per 3s into `work/frames/` (98 frames) and built a 10x10 contact sheet.
- Identified the source as Epicurious "50 People Try / Pancakes". Found the expert section by spotting the chef in a white coat with an ICE badge ("Frank Proto, Chef Instructor").
- Narrowed expert range to ~165s-264s, then sampled 1 fps into `work/expertframes/` and built finer 5x20 / 10x10 sheets to identify each beat.

## Plan
Five-cut tutorial, ~60s total, true 9:16 portrait crop, burned step captions:
1. 165-172 (7s) Chef intro - center crop
2. 175-185 (10s) Butter pan - right-shifted crop (pan top-down sits right-of-center)
3. 187-202 (15s) Ladle batter - right-shifted crop
4. 205-220 (15s) Cook until golden - right-shifted crop
5. 241-254 (13s) Plate the pancake - right-shifted crop

Two crop offsets used: `crop=405:720:438:0` (center) for the wide workbench intro where the chef is centered; `crop=405:720:600:0` (right-shifted) for the top-down cooking shots so the pan, hands, pancake, and plate stay in the vertical frame. Scaled to 1080x1920.

## Execution
- For each segment ran `ffmpeg -ss S -t T -i source.mp4 -vf crop+scale -c:v libx264 -crf 20 -c:a aac` -> `work/c1..c5.mp4`.
- Concatenated with `ffmpeg -f concat` to `work/concat.mp4`.
- Single ffmpeg pass to burn 5 captions via `drawtext` (yellow "Step N" + white description, top-center, with black border for readability) and apply `loudnorm=I=-16:TP=-1.5:LRA=11`.
- Encoded final to H.264 yuv420p / AAC 48kHz, `+faststart`, written to `submit/output.mp4`.

## Notable issues / fixes
- Initial concern that center crop would lose the pan in the top-down shots. Verified with sampled cropped frames (`work/c4_check.jpg`) and switched the cooking segments to offset 600 so the pan and pancake remain centered in the vertical frame.

## Final validation
- `ffprobe submit/output.mp4`: H.264 1080x1920, AAC stereo 48000 Hz, duration 60.227s (inside 55-65s target).
- Sampled output frames at t=3, 22, 50 -> captions render correctly; chef/pan/plate visible.
- `librosa` check: max abs sample 0.86 (no clipping), RMS 0.111, silent fraction 0.035 (no silent padding).
- Verified no novice/blooper content included; source ranges all within 165-254s expert block.
- Verified true vertical crop (no letterbox / blur padding).
