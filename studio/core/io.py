"""FFmpeg/FFprobe wrappers: probe, streamed frame reading, streamed encoding."""
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Iterator

import numpy as np

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = shutil.which("ffprobe") or "ffprobe"


@dataclass
class MediaInfo:
    path: str
    duration: float
    width: int | None
    height: int | None
    fps: float | None
    vcodec: str | None
    acodec: str | None
    sample_rate: int | None
    pix_fmt: str | None
    size_bytes: int
    nb_frames: int | None

    @property
    def has_video(self) -> bool:
        return self.width is not None

    @property
    def has_audio(self) -> bool:
        return self.acodec is not None


def probe(path: str | Path) -> MediaInfo:
    out = subprocess.run(
        [FFPROBE, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout
    data = json.loads(out)
    v = next((s for s in data["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in data["streams"] if s["codec_type"] == "audio"), None)
    fps = float(Fraction(v["avg_frame_rate"])) if v and v.get("avg_frame_rate", "0/0") != "0/0" else None
    return MediaInfo(
        path=str(path),
        duration=float(data["format"].get("duration", 0.0)),
        width=v and int(v["width"]), height=v and int(v["height"]), fps=fps,
        vcodec=v and v["codec_name"], acodec=a and a["codec_name"],
        sample_rate=a and int(a["sample_rate"]), pix_fmt=v and v.get("pix_fmt"),
        size_bytes=int(data["format"].get("size", 0)),
        nb_frames=int(v["nb_frames"]) if v and v.get("nb_frames", "").isdigit() else None,
    )


def read_frames(path: str | Path, width: int | None = None, height: int | None = None,
                start: float = 0.0, duration: float | None = None, fps: float | None = None) -> Iterator[np.ndarray]:
    """Yield uint8 RGB frames, optionally resized / trimmed / resampled by ffmpeg."""
    info = probe(path)
    w, h = width or info.width, height or info.height
    vf = [f"scale={w}:{h}"] if (w, h) != (info.width, info.height) else []
    if fps:
        vf.insert(0, f"fps={fps}")
    cmd = [FFMPEG, "-v", "error", "-ss", f"{start:.3f}", "-i", str(path)]
    if duration is not None:
        cmd += ["-t", f"{duration:.3f}"]
    if vf:
        cmd += ["-vf", ",".join(vf)]
    cmd += ["-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    frame_bytes = w * h * 3
    try:
        while True:
            buf = proc.stdout.read(frame_bytes)
            if len(buf) < frame_bytes:
                break
            yield np.frombuffer(buf, np.uint8).reshape(h, w, 3)
    finally:
        proc.stdout.close()
        proc.wait()


def read_frame_at(path: str | Path, t: float, width: int | None = None, height: int | None = None) -> np.ndarray | None:
    return next(read_frames(path, width, height, start=t, duration=1.0), None)


def read_audio(path: str | Path, sample_rate: int = 48000, mono: bool = False,
               start: float = 0.0, duration: float | None = None) -> np.ndarray:
    """Decode audio to float32 array shaped (samples, channels)."""
    ch = 1 if mono else 2
    cmd = [FFMPEG, "-v", "error", "-ss", f"{start:.3f}", "-i", str(path)]
    if duration is not None:
        cmd += ["-t", f"{duration:.3f}"]
    cmd += ["-vn", "-ac", str(ch), "-ar", str(sample_rate), "-f", "f32le", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).reshape(-1, ch).copy()


class VideoWriter:
    """Pipe RGB frames into ffmpeg/libx264. Optional audio file is muxed in at close."""

    def __init__(self, path: str | Path, width: int, height: int, fps: float, crf: int = 18,
                 preset: str = "medium", codec: str = "libx264", pix_fmt: str = "yuv420p",
                 audio_path: str | Path | None = None, audio_bitrate: str = "192k",
                 extra_args: list[str] | None = None):
        self.path, self.width, self.height = str(path), width, height
        cmd = [FFMPEG, "-y", "-v", "error",
               "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{width}x{height}", "-r", f"{fps}", "-i", "-"]
        if audio_path:
            cmd += ["-i", str(audio_path)]
        cmd += ["-map", "0:v:0"]
        if audio_path:
            cmd += ["-map", "1:a:0", "-c:a", "aac", "-b:a", audio_bitrate, "-shortest"]
        cmd += ["-c:v", codec, "-preset", preset, "-crf", str(crf), "-pix_fmt", pix_fmt,
                "-movflags", "+faststart", *(extra_args or []), self.path]
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        self.frames = 0

    def write(self, frame: np.ndarray) -> None:
        if frame.dtype != np.uint8:
            frame = (np.clip(frame, 0, 1) * 255 + 0.5).astype(np.uint8)
        if frame.shape[:2] != (self.height, self.width):
            raise ValueError(f"frame {frame.shape[:2]} != writer {(self.height, self.width)}")
        self.proc.stdin.write(np.ascontiguousarray(frame).tobytes())
        self.frames += 1

    def close(self) -> None:
        self.proc.stdin.close()
        err = self.proc.stderr.read().decode(errors="replace")
        if self.proc.wait() != 0:
            raise RuntimeError(f"ffmpeg failed writing {self.path}: {err.strip()}")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, *_):
        if exc_type is None:
            self.close()
        else:
            self.proc.kill()


def run_ffmpeg(args: list[str]) -> subprocess.CompletedProcess:
    proc = subprocess.run([FFMPEG, "-y", "-v", "error", *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc
