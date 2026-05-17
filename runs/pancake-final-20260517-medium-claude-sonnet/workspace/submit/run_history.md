# Run History — Expert Pancake Tutorial Extraction

## 1. Detection Phase

**Source inspection:**
- File: `materials/source.mp4`
- Duration: 293s (~4m53s)
- Resolution: 1280×720, 16:9 landscape
- Codec: H.264/AAC, ~24fps
- Format: "50 People Try to Make Pancakes" (Epicurious)

**Frame sampling:**
- Extracted 1fps frames (293 total) via `ffmpeg -vf fps=1`
- Created 4 contact sheets (0-80s, 80-160s, 160-240s, 240-293s)
- Created detail views for 155-185s and 240-270s transition periods

**Content analysis from frames:**
- 0-163s: Novice section — title card at ~5s, then 50+ people making pancakes with varying (mostly poor) results. Shows failures, confused faces, burned pancakes, novelty molds.
- 163-265s: Expert section — Chef Frank Proto (from ICE, Institute of Culinary Education) demonstrates proper pancake technique step-by-step. Identifiable by white chef coat, red ICE logo badge, name lower-third overlay.
- 265-280s: People's reactions, holding plates with finished pancakes
- 280-293s: Epicurious end card / logo

## 2. Planning Phase

**Expert section identified:** 164s–265s (~101s total)

**Key steps extracted from visual inspection:**
1. Chef intro/establishing shot: 164–168.5s
2. Add butter, heat pan (top-down): 173.5–181.5s
3. Pour batter (wide + top-down): 183.5–189.5s
4. Cook until bubbles form (top-down): 196–207s
5. Flip once (top-down): 230.5–240.5s
6. Plate and serve (top-down + chef face): 247–263s

**Target duration:** 55–65s; planned total = ~55.7s ✓

**Portrait crop strategy:**
- Source: 1280×720 (16:9)
- Crop: 405×720 region (9:16 aspect ratio), centered at x=430
- Scale: 405×720 → 720×1280
- Zoom factor: ~1.78× — keeps chef, hands, pan, and spatula in frame
- No black bars, blurred padding, or letterboxing

**Captions plan:** 6 burned-in step labels at segment boundaries, white text with dark background box.

## 3. Tool Execution

**Step 1 — Segment extraction with portrait crop:**
```
ffmpeg -ss {start} -to {end} -i source.mp4 -vf "crop=405:720:430:0,scale=720:1280" ...
```
Extracted 6 segments; all confirmed correct durations via ffprobe.

**Step 2 — Concatenation:**
```
ffmpeg -f concat -safe 0 -i concat.txt ... work/combined.mp4
```
Combined duration: 55.765s

**Step 3 — Audio normalization:**
```
ffmpeg -af "loudnorm=I=-16:TP=-1.5:LRA=11" ...
```
Result: I=-16.4 LUFS, TP=-1.0 dBFS — within spec, no clipping.

**Step 4 — Burn-in captions:**
```
ffmpeg -vf "drawtext=text='Step N: ...':enable='between(t,T1,T2)':..." ...
```
6 captions with black background box, fontsize=44, bottom-center position.

**Output:** `submit/output.mp4`

## 4. Final Validation

| Check | Result |
|---|---|
| Duration | 55.765s ✓ (target: 55–65s) |
| Resolution | 720×1280 ✓ (portrait 9:16) |
| Video codec | H.264 ✓ |
| Audio codec | AAC ✓ |
| Audio loudness | I=-16.4 LUFS ✓ |
| True peak | -1.0 dBFS ✓ (no clipping) |
| Black frames | None detected ✓ |
| Portrait crop | True crop, no black bars ✓ |
| Captions visible | Yes, all 6 steps ✓ |
| Expert content | Frank Proto only, no novice bloopers ✓ |
| End card / reactions | Excluded ✓ |
