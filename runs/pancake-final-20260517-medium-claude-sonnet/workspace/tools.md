# Available Tools

This sandbox is CPU-only. Do not assume GPU availability.

## Shell Commands

- `ffmpeg`
- `ffprobe`
- `python`
- `bash`

## Python Packages

- `numpy`
- `scipy`
- `cv2`
- `moviepy`
- `av`
- `librosa`
- `soundfile`
- `pydub`
- `scenedetect`
- `PIL`
- `skimage`
- `pandas`
- `pydantic`
- `tqdm`
- `colour`
- `noisereduce`
- `imageio`
- `imageio_ffmpeg`
- `matplotlib`
- `jsonschema`

## Useful Commands

Probe video:

```bash
ffprobe -v error -print_format json -show_format -show_streams materials/source.mp4
```

Extract mono 16 kHz audio:

```bash
mkdir -p work
ffmpeg -y -i materials/source.mp4 -vn -ac 1 -ar 16000 work/audio.wav
```

Sample one frame per second:

```bash
mkdir -p work/frames
ffmpeg -y -i materials/source.mp4 -vf fps=1 work/frames/frame_%04d.jpg
```

Create a contact sheet from sampled frames:

```bash
ffmpeg -y -pattern_type glob -i 'work/frames/*.jpg' -vf tile=5x5 work/contact_sheet.jpg
```

Validate output:

```bash
ffprobe -v error -print_format json -show_format -show_streams submit/output.mp4
```

Check duration only:

```bash
ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 submit/output.mp4
```

## Notes

- Keep temporary files inside `work/` or another workspace-local directory.
- Final files must go under `submit/`.
- Do not look for hidden ground truth, verifier code, private task files, or files outside the workspace.
