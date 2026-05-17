# Agent Transcript — Expert Pancake Tutorial Extraction

## Session Overview

Task: Extract a 55–65 second vertical (9:16) expert pancake tutorial from a 293s "50 People Try to Make Pancakes" Epicurious video.

---

## Phase 1: Source Inspection

**Action:** Read `tools.md` and `prompt.md` to understand constraints.

**Action:** `ffprobe materials/source.mp4` →
- 1280×720 landscape, H.264/AAC, 293.083s, ~24fps (~40MB)

**Action:** Extracted 293 frames at 1fps with ffmpeg, then used Python/OpenCV to produce 4 contact-sheet images covering the full video.

**Observation from contact sheets:**
- Seconds 0–163: Title card, then ~50 people attempting pancakes. Mix of novice failures, burned results, confused faces, novelty pans (silicone mold rings), and bloopers.
- Seconds 163–265: A professional chef in a white coat with a red ICE (Institute of Culinary Education) badge. Name overlay: "Frank Proto." Works at a prep table with two cast iron pans, a bowl of batter, and butter. Clean, methodical technique.
- Seconds 265–280: Participant reactions, people holding plated pancakes.
- Seconds 280–293: Epicurious branded end card.

**Action:** Created detail frame grids at 155–185s and 240–270s to find precise transition timestamps.

**Finding:** Expert section starts at ~164s (after the novelty-mold person's shot ends). End of useful expert content at ~263s.

---

## Phase 2: Edit Planning

**Identified 6 cooking steps** from the expert section:

| # | Label | Source range | Duration |
|---|---|---|---|
| 0 | Intro | 164.0–168.5s | 4.5s |
| 1 | Add butter | 173.5–181.5s | 8.0s |
| 2 | Pour batter | 183.5–189.5s | 6.0s |
| 3 | Cook (bubbles) | 196.0–207.0s | 11.0s |
| 4 | Flip | 230.5–240.5s | 10.0s |
| 5 | Plate & serve | 247.0–263.0s | 16.0s |

Total planned: **55.5s** (within 55–65s target)

**Portrait crop decision:**
- Crop 405×720 from center of 1280×720 source (x=430)
- Scale to 720×1280 (9:16) — zoom factor ~1.78×
- Center crop was verified against key frames: captures chef face, hands, pan, spatula, and plate across all shots
- No padding, borders, or blurred background

---

## Phase 3: Tool Execution

**Script 1 — Segment extraction:**
```bash
# For each segment:
ffmpeg -ss {start} -to {end} -i materials/source.mp4 \
  -vf "crop=405:720:430:0,scale=720:1280" \
  -c:v libx264 -preset fast -crf 22 -c:a aac -b:a 128k \
  work/segments/seg_NN_label.mp4
```
All 6 segments extracted cleanly. Durations confirmed via ffprobe.

**Script 2 — Concatenation:**
```bash
ffmpeg -f concat -safe 0 -i concat.txt \
  -c:v libx264 -preset fast -crf 22 -c:a aac -b:a 128k \
  work/combined.mp4
# Duration: 55.765s
```

**Script 3 — Audio normalization:**
```bash
ffmpeg -i work/combined.mp4 \
  -af "loudnorm=I=-16:TP=-1.5:LRA=11" \
  -c:v copy -c:a aac -b:a 128k \
  work/normalized.mp4
```

**Script 4 — Burned-in captions:**
Six drawtext overlays via ffmpeg `-vf`, each time-gated with `enable='between(t,T1,T2)'`:
- `Frank Proto | Chef Instructor, ICE` (0–4.5s)
- `Step 1: Heat pan & add butter` (4.5–12.6s)
- `Step 2: Pour in your batter` (12.6–18.6s)
- `Step 3: Cook until bubbles form` (18.6–29.6s)
- `Step 4: Flip once — golden side up!` (29.6–39.7s)
- `Step 5: Plate & serve warm` (39.7–55.8s)

Output written to: `submit/output.mp4`

---

## Phase 4: Final Validation

**Action:** `ffprobe submit/output.mp4`
- Resolution: 720×1280 ✓ (true 9:16 portrait)
- Duration: 55.765s ✓ (within 55–65s)
- Video: H.264, 24fps ✓
- Audio: AAC stereo ✓

**Action:** `ffmpeg -af ebur128=peak=true -f null -`
- Integrated loudness: -16.4 LUFS ✓
- True peak: -1.0 dBFS ✓ (no clipping)

**Action:** `ffmpeg -vf blackdetect` → No black frames detected ✓

**Action:** Sampled 11 output frames at 0.2fps, reviewed visually:
- All frames show chef, hands, pan, or plating in portrait crop ✓
- Captions visible in correct segments ✓
- No black bars, blurred padding, or letterboxing ✓
- Cooking action continuously visible ✓

**Result:** All checks passed. `submit/output.mp4` is a 55.77s 720×1280 H.264/AAC portrait video of the expert pancake tutorial with burned-in step captions and normalized audio.
