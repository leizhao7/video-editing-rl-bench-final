# Task: Rough Interview Cleanup and Captioning

You are editing a rough interview excerpt into a polished educational social clip.

Input:
- `materials/source.mp4` is a rough 16:9 interview excerpt.

Create:
- `submit/output.mp4`
- `submit/captions.srt`
- `submit/edit_decision.json`
- `submit/run_history.md`
- `submit/agent_transcript.md`

Output requirements:
- 60-75 seconds total duration.
- 1280x720, 16:9, H.264 video with AAC audio.
- Preserve a clear self-contained explanation about helping young people stay motivated and thrive at work.
- Remove long dead air, obvious false starts, and repeated phrase loops while keeping speech natural.
- Keep the main speaker's meaning intact. Do not reorder ideas in a way that changes the argument.
- Normalize spoken audio so it is comfortably listenable without clipping or pumping.
- Add readable burned-in captions for all spoken words, and save the timing as `submit/captions.srt`.
- Avoid black frames, frozen frames, unrelated footage, background music, synthetic narration, and heavy decorative overlays.

In `submit/edit_decision.json`, list kept source segments, removed defects or pauses, audio filters,
subtitle generation method, caption style, and measured self-checks.

Also write `submit/run_history.md` and `submit/agent_transcript.md` with your action log and
observable work transcript/summary.
