# Run History

1. Probed `materials/source.mp4` with `ffprobe` and confirmed a 293.08 s landscape source at 1280x720 with AAC audio.
2. Extracted mono 16 kHz audio and sampled frames at 1 fps, then built contact sheets to locate the tutorial-worthy section.
3. Identified the cleanest expert stretch in the chef segment around 200-262 s. It covers battering, cooking, flipping, and plating without relying on bloopers or unrelated banter.
4. Tested a portrait crop on short samples. The first caption attempt clipped because the step text was too long on one line, so I switched to text files with explicit line breaks.
5. The first full render attempt failed on an audio filter chain using `aresample`; I replaced it with `aformat=sample_rates=48000:channel_layouts=stereo` after `loudnorm`, which rendered successfully.
6. Rendered `submit/output.mp4` as a 62.0 s 720x1280 H.264/AAC vertical short with burned-in step captions.
7. Validated the final output with `ffprobe`, frame sampling, `volumedetect`, `silencedetect`, and a Python frame continuity check.

Validation results:

- Duration: 62.000 s container duration, 61.9786 s video stream duration.
- Video: H.264, 720x1280, SAR 1:1, DAR 9:16.
- Audio: AAC stereo, 48 kHz.
- Loudness: mean_volume -19.7 dB, max_volume -1.3 dB.
- Silence: no silence spans detected with `silencedetect`.
- Visual continuity: 62 sampled frames, no dark frames below luma 15, minimum sampled frame difference 3.36.
