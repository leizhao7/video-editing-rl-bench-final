from __future__ import annotations

import subprocess
from pathlib import Path


def run_ffmpeg(args: list[str | Path], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *[str(arg) for arg in args]]
    return subprocess.run(cmd, check=check, capture_output=True, text=True)


def transcode_clip(
    *,
    source: Path,
    output: Path,
    start_sec: float | None = None,
    end_sec: float | None = None,
    resolution: tuple[int, int] | None = None,
    fps: int | None = None,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    args: list[str | Path] = []
    if start_sec is not None:
        args += ["-ss", f"{start_sec:.3f}"]
    args += ["-i", source]
    if start_sec is not None and end_sec is not None:
        args += ["-t", f"{max(0.01, end_sec - start_sec):.3f}"]
    elif end_sec is not None:
        args += ["-t", f"{end_sec:.3f}"]

    vf: list[str] = []
    if resolution:
        width, height = resolution
        vf.append(
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1"
        )
    if fps:
        vf.append(f"fps={fps}")
    if vf:
        args += ["-vf", ",".join(vf)]

    args += [
        "-map",
        "0:v:0",
        "-map",
        "0:a:0?",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-c:a",
        "aac",
        "-ar",
        "48000",
        "-ac",
        "2",
        "-movflags",
        "+faststart",
        output,
    ]
    run_ffmpeg(args)


def concat_mp4(parts: list[Path], output: Path, *, work_dir: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    concat_file = work_dir / "concat.txt"
    concat_file.write_text("".join(f"file '{part.resolve()}'\n" for part in parts))
    run_ffmpeg(
        [
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            concat_file,
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            output,
        ]
    )


def make_black_clip(output: Path, duration_sec: float, *, resolution: tuple[int, int] = (1280, 720), fps: int = 30) -> None:
    width, height = resolution
    run_ffmpeg(
        [
            "-f",
            "lavfi",
            "-i",
            f"color=c=black:s={width}x{height}:r={fps}:d={duration_sec:.3f}",
            "-f",
            "lavfi",
            "-i",
            f"anullsrc=channel_layout=stereo:sample_rate=48000",
            "-t",
            f"{duration_sec:.3f}",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-c:a",
            "aac",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-shortest",
            output,
        ]
    )


def make_freeze_clip(
    *,
    source: Path,
    source_time_sec: float,
    output: Path,
    work_dir: Path,
    duration_sec: float,
    resolution: tuple[int, int] = (1280, 720),
    fps: int = 30,
) -> None:
    frame = work_dir / f"{output.stem}.png"
    width, height = resolution
    run_ffmpeg(["-ss", f"{source_time_sec:.3f}", "-i", source, "-frames:v", "1", frame])
    run_ffmpeg(
        [
            "-loop",
            "1",
            "-t",
            f"{duration_sec:.3f}",
            "-i",
            frame,
            "-f",
            "lavfi",
            "-i",
            "anullsrc=channel_layout=stereo:sample_rate=48000",
            "-vf",
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-c:a",
            "aac",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-shortest",
            output,
        ]
    )


def make_shifted_segment(
    *,
    source: Path,
    output: Path,
    start_sec: float,
    duration_sec: float,
    audio_delay_ms: int,
    resolution: tuple[int, int] = (1280, 720),
    fps: int = 30,
) -> None:
    width, height = resolution
    video_filter = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps},setpts=PTS-STARTPTS"
    )
    if audio_delay_ms >= 0:
        audio_filter = (
            "aresample=48000,aformat=channel_layouts=stereo,"
            f"adelay={audio_delay_ms}|{audio_delay_ms},"
            f"atrim=0:{duration_sec:.3f},asetpts=PTS-STARTPTS"
        )
    else:
        advance_sec = abs(audio_delay_ms) / 1000.0
        audio_filter = (
            "aresample=48000,aformat=channel_layouts=stereo,"
            f"atrim=start={advance_sec:.3f},asetpts=PTS-STARTPTS,"
            f"apad=pad_dur={advance_sec:.3f},"
            f"atrim=0:{duration_sec:.3f},asetpts=PTS-STARTPTS"
        )
    run_ffmpeg(
        [
            "-ss",
            f"{start_sec:.3f}",
            "-t",
            f"{duration_sec:.3f}",
            "-i",
            source,
            "-filter_complex",
            f"[0:v]{video_filter}[v];[0:a]{audio_filter}[a]",
            "-map",
            "[v]",
            "-map",
            "[a]",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-c:a",
            "aac",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-movflags",
            "+faststart",
            output,
        ]
    )
