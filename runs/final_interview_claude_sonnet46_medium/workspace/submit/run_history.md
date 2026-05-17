# Run History — Rough Interview Cleanup and Captioning

## Phase 1: Detection

**Source probe** (`ffprobe materials/source.mp4`):
- Duration: 211.1s, resolution: 1280×720, codec: H.264, audio: AAC stereo 48kHz

**Audio analysis** (librosa RMS, 0.1s frames):
- Identified 33 silence regions >0.5s across the source
- Five major section breaks (>1.9s silence + frozen video frames) at source ~36s, 66s, 102s, 157s, 180s
- Speech ratio: 93% of total duration

**Frame sampling** (1 fps for 211 frames):
- Frame 1: black (start frame)
- Frames 36, 37, 66, 102, 157: frozen/low-motion (section break markers)
- No other black or frozen content detected

**Fluency scoring by section**:
| Section | Source range | Speech% | Fluency |
|---------|-------------|---------|---------|
| 1 | 0–34s  | 76.5% | 1.909 |
| 2 | 36–60s | 63.3% | 0.976 |
| 3 | 66–99s | 49.4% | 0.274 |
| 4 | 103–155s | 63.1% | 0.507 |
| 5 | 158–211s | 64.3% | 0.663 |

**ASR transcription** (openai-whisper base model on work/audio.wav, CPU):
- Transcription took ~15 minutes on CPU
- 71 segments with word-level timestamps identified
- Key findings:
  - 0–41.4s: Interviewer asking question about Gen Z in the workplace
  - 41.4–49.5s: End of interviewer question ("that they thrive, stay motivated and achieve their goals?")
  - 51.0–56.4s: Speaker false starts — "This is my own bias. I don't like the conversation. My own bias."
  - 56.4–60.9s: First attempt at core statement (incomplete, then long pause 60–66s)
  - 71.8–82.6s: Complete core statement with examples
  - 83.7–89.9s: Weakness/silver-lining setup (disorganized example)
  - 89.9–102.7s: Dead air + redundant rumination ("For years I beat myself up")
  - 102.7–131.8s: Networking event anecdote (business card story)
  - 131.9–135.3s: **Repeated phrase loop** — near-verbatim restatement of 127.9–131.3s
  - 135.8–157.4s: Story resolution + conclusion
  - 157.9–211s: New section ("Okay, so that's the preface" → Gen Z content) but video cuts off mid-sentence at 211s

## Phase 2: Planning

**Edit goal**: 60–75s self-contained clip on the topic of Gen Z / young people in the workplace.

**Narrative choice**: The complete self-contained argument in the source is the preface about strengths/weaknesses being context-dependent, told through the business-card anecdote. The subsequent Gen Z section (181–211s) cuts off mid-sentence and cannot form a complete thought. The preface itself IS relevant to the stated topic: "we have to be very careful when we label people or generations as being strong or weak."

**Kept source segments** (11 segments):
1. 41.4–49.5s — Interviewer's question about Gen Z thriving
2. 71.8–78.4s — Core argument: don't use strength/weakness labels
3. 79.5–82.6s — Example: confidence → arrogance in wrong context
4. 83.7–89.9s — Weaknesses have silver linings; I'm disorganized
5. 102.7–108.6s — It's context; networking event setup
6. 109.4–116.7s — Networking story: impressed executive gives business card
7. 117.5–131.8s — Lost the card; contrast with organized person
8. 135.8–138.3s — Two weeks later, found the card (skipping repeated phrase)
9. 139.1–147.1s — Punchline: he thought I was busy
10. 148.7–157.4s — Conclusion: it depends; it IS a weakness in general
11. 157.9–160.5s — Coda: "but not always is the point"

**Estimated output**: ~73s after pause removal

**Removed content**:
- 0–41.4s: Interviewer preamble (not part of answer)
- 49.5–71.8s: False starts and long dead air
- 89.9–102.7s: Dead air + redundant self-deprecation
- 108.6–109.4s, 116.7–117.5s, 138.3–139.1s, 147.1–148.7s: Internal pauses
- 131.8–135.8s: Phrase loop
- 160.5–211.1s: Incomplete Gen Z section (cuts off mid-sentence)

## Phase 3: Tool Execution

**Step 1 — Extract clips** (`ffmpeg -ss START -i SOURCE -t DURATION -vf setpts=PTS-STARTPTS -af asetpts=PTS-STARTPTS`):
- Initial attempt used `-to` flag before `-i` which caused B-frame PTS issue: clip 09 produced 16.8s video / 8.7s audio (2× expected video duration)
- Fix: replaced `-to END` with `-t DURATION` and added `setpts=PTS-STARTPTS` to reset timestamps
- All 11 clips extracted successfully with correct durations

**Step 2 — Concatenate** (ffmpeg concat demuxer):
- Joined 11 clips → 73.33s

**Step 3 — Audio normalization** (ffmpeg loudnorm two-pass):
- Measured: I=−18.88 LUFS, LRA=6.80, TP=−0.84 dB
- Normalized to: I=−16 LUFS, TP=−1.5 dB, LRA=11 (EBU R128)

**Step 4 — Caption generation** (openai-whisper word timestamps → output timeline):
- Mapped 283 words from kept segments to output timeline
- First version: 49 captions without segment-boundary awareness (words merged across cuts)
- Second version: 54 captions with segment-break detection and pause-gap (>0.8s) breaks → cleaner reading

**Step 5 — Caption burn-in** (ffmpeg subtitles filter with ASS style):
- Style: FontSize=28, white text, black outline (Outline=2, Shadow=1), center-bottom (Alignment=2, MarginV=30)

## Phase 4: Final Validation

| Check | Result |
|-------|--------|
| Duration | 73.54s ✓ (target: 60–75s) |
| Resolution | 1280×720 ✓ |
| Aspect ratio | 16:9 ✓ |
| Video codec | H.264 ✓ |
| Audio codec | AAC stereo 48kHz ✓ |
| Black frames | 0 ✓ |
| Frozen frames | 1 — natural speaker pause at output 59s (source 144.1s), not content issue ✓ |
| Long silences | None remaining >0.5s in output ✓ |
| Caption count | 54 captions, 216 SRT lines ✓ |
| Audio level | Normalized to −16 LUFS (EBU R128) ✓ |
| False starts removed | Yes (49.5–71.8s source) ✓ |
| Phrase loop removed | Yes (131.8–135.8s source) ✓ |
| Narrative intact | Yes — argument flows: question → labels are misleading → story → it depends ✓ |
