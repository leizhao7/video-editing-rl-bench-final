1. Detected source metadata with `ffprobe`: 1280x720 H.264/AAC MP4, 101.782 s, 30 fps, stereo audio.
2. Sampled frames and audio:
   - Built a 1 fps contact sheet to map visual structure.
   - Ran `silencedetect`, `blackdetect`, and `freezedetect` on the source.
   - Found a black leader at the start, a frozen/repeated screenshot stretch around 32.3-37.3 s, and a black/silent tail at the end.
3. Planned a conservative edit:
   - Keep the tutorial in original order.
   - Remove the black leader, the static/repeated screenshot section, and the trailing dead air.
   - Normalize speech loudness and export a standard landscape MP4.
4. Rendered an initial trim-only export, then re-rendered with an explicit 48 kHz AAC target so the audio stream used a standard sample rate.
5. Rendered the final cut with two retained ranges:
   - 1.2-32.3 s
   - 37.3-98.8 s
   and applied `loudnorm`, `scale=1280:720`, and `setsar=1`.
6. Verified the final file:
   - `ffprobe` showed 92.6 s duration, H.264 video, AAC audio, 1280x720, SAR 1:1, 30 fps.
   - `volumedetect` showed max_volume -0.6 dB, with no clipping.
   - `blackdetect` and `freezedetect` found no remaining black/frozen spans.
   - `silencedetect` showed only short natural pauses.
   - Sampled output frames to confirm the content stayed in order and the ending was clean.
