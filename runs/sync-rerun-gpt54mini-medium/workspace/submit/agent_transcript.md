# Work Transcript Summary

## Detection
- Inspected `materials/source.mp4` with `ffprobe`.
- Extracted one frame per second and assembled a contact sheet to inspect the clip structure.
- Ran audio and video diagnostics:
  - `silencedetect`
  - `blackdetect`
  - `freezedetect`

Observed issues:
- Black leader at the start.
- Frozen/repeated static screenshot section around 32.3-37.3 s.
- Black/silent tail at the end.
- Source duration was 101.782 s, longer than the required 88-98 s window.

## Planning
- Chosen repair strategy:
  - Preserve the tutorial's original order.
  - Remove only the non-content/problem sections.
  - Normalize speech loudness.
  - Export a standard 1280x720 H.264/AAC MP4.

## Execution
- First render:
  - Trimmed the front and tail.
  - Normalized audio with `loudnorm`.
  - Result revealed AAC at 96 kHz, which is playable but not the cleanest standard export.
- Second render:
  - Forced AAC to 48 kHz.
  - Kept the same trim and loudness normalization.
- Final render:
  - Removed three ranges by concatenating the retained segments:
    - 1.2-32.3 s
    - 37.3-98.8 s
  - Applied `scale=1280:720`, `setsar=1`, and `loudnorm=I=-16:TP=-1.5:LRA=11:linear=true`.
  - Wrote `submit/output.mp4`.

## Validation
- `ffprobe submit/output.mp4`
  - H.264 video
  - AAC audio
  - 1280x720
  - 1:1 SAR
  - 30 fps
  - 92.6 s duration
- `volumedetect`
  - mean_volume: -21.5 dB
  - max_volume: -0.6 dB
- `blackdetect` on output: no black spans found.
- `freezedetect` on output: no frozen spans found.
- `silencedetect` on output: only short natural pauses remained.
- Sampled output frames to confirm the edit preserved the tutorial flow and ended cleanly.
