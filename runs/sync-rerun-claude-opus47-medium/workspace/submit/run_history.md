# Run History

## 1. Inspection
- `ffprobe materials/source.mp4`: 101.78s, H.264 1280x720 30fps SAR 1:1, AAC 48kHz stereo.
- Read `source_metadata.json` and `output_specs.json`: task `piecewise_av_sync_repair`, target landscape 1280x720, duration gate 88-98s (target 90-96s).
- Extracted audio (`work/audio.wav`, mono 16kHz) and analyzed RMS in 0.5s windows with librosa.
- Extracted frames at 2 fps to `work/frames/` and computed mean brightness per frame.
- Built a contact sheet (`work/contact.jpg`) to visually map the timeline.

## 2. Issues identified
- Head: black/empty frames 0.0-1.5s.
- 2.0-4.0s: branded intro graphics ("THE VIDEO SHOW") — not tutorial body.
- 49.0-51.0s: sustained near-total silence (RMS < -180 dB) = dead air.
- 100.0-101.78s: trailing black/empty frames.
- Speech loudness varied widely (-45 to -22 dB RMS) across the clip.

## 3. Edit plan
Two-segment keep with the silence gap removed:
- Keep src 4.0-49.0 (tutorial part 1, includes clap demo + creator-clap explanation).
- Drop src 49.0-51.0 (dead air).
- Keep src 51.0-100.0 (tutorial part 2 through end of useful content).
- Total: 94.0s (inside both 88-98 gate and 90-96 target).
Apply loudnorm to even out speech without clipping or muting.

## 4. Render
Single ffmpeg invocation using filter_complex with trim/atrim + concat + loudnorm, encoded to libx264/aac, 1280x720, 30 fps, yuv420p, +faststart.

## 5. Final validation
- `ffprobe submit/output.mp4`: duration 94.000s, h264 1280x720 30/1, aac 2ch.
- Duration within gate (88-98s) and target (90-96s). Square pixels preserved. Audio stream present.
- Visual spot-check of frames confirms tutorial content preserved in original order.
