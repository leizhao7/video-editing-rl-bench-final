# Task: Piecewise A/V Sync and Damage Repair

You are given `materials/source.mp4`, a damaged 16:9 tutorial excerpt from a creator.

The clip has multiple technical defects:
- audio/video sync is wrong by different amounts in different parts of the clip;
- there is black leader and black tail;
- there is one accidental freeze/dead-air splice;
- speech loudness is uneven and there may be mild hum/noise.

Create:
- `submit/output.mp4`
- `submit/edit_decision.json`

Requirements:
1. Repair A/V sync locally. Do not assume a single global audio offset is enough.
2. Remove black leader/tail and the accidental freeze/dead-air splice.
3. Preserve the useful tutorial content in original order, including the clap demonstration and the
   explanation of why creators clap before takes.
4. Keep natural pacing. Do not delete explanation just to make sync easier.
5. Normalize speech loudness without clipping, muting, or replacing the original audio.
6. Export a standard landscape MP4: H.264 video, AAC audio, 1280x720, square pixels, 24-30 fps,
   duration 88-98 seconds.
7. Do not add external footage, synthetic speech, unrelated music, large overlays, or face-covering text.
8. Write `submit/edit_decision.json` with segment cuts, estimated local audio shifts, removed damage
   ranges, filters used, and measured self-checks.
