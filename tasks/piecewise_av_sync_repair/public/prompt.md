# Task: Repair a Damaged Tutorial Clip

You are given `materials/source.mp4`, a rough 16:9 export of a creator tutorial.

Create:
- `submit/output.mp4`
- `submit/edit_decision.json`
- `submit/run_history.md`
- `submit/agent_transcript.md`

Requirements:
1. Inspect the media and identify technical issues that would make the clip unsuitable for publishing.
2. Produce a clean 16:9 MP4 that preserves the useful tutorial content in original order.
3. Keep the clap demonstration and the explanation of why creators clap before takes if they are
   useful to the final edit.
4. Remove non-content artifacts, repeated or broken material, dead air, and unusable sections.
5. Repair any audio/video timing issues you find.
6. Normalize speech loudness without clipping, muting, or replacing the original audio.
7. Export a standard landscape MP4: H.264 video, AAC audio, 1280x720, square pixels, 24-30 fps,
   duration 88-98 seconds.
8. Do not add external footage, synthetic speech, unrelated music, large overlays, or face-covering text.
9. Write `submit/edit_decision.json` with the issues you found, segment cuts, timing repairs,
   removed ranges, filters used, and measured final validation checks.
10. Write `submit/run_history.md` and `submit/agent_transcript.md` with your action log and
   observable work transcript/summary.
