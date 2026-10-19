"""Preview / Final render modes on top of Timeline.render.

Every render:
  * gets a fresh versioned filename (never overwrites) via studio.versioning
  * writes a JSON render record next to the video and appends to renders.jsonl
  * Final mode loudness-normalises audio (two-pass loudnorm) to the configured LUFS / true peak
  * Preview mode re-encodes at higher CRF until the file fits `max_size_mb`
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .. import versioning
from ..config import REPO_ROOT, load_config
from ..core.io import probe, run_ffmpeg
from ..core.timeline import Timeline


@dataclass
class RenderResult:
    path: str
    mode: str
    version: int
    width: int
    height: int
    fps: float
    duration: float
    size_mb: float
    seconds: float
    range: tuple[float, float]
    crf: int
    audio: dict = field(default_factory=dict)
    git_commit: str | None = None
    project_id: str | None = None
    created_at: str = ""


def git_commit() -> str | None:
    try:
        sha = subprocess.run(["git", "-C", str(REPO_ROOT), "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "-C", str(REPO_ROOT), "status", "--porcelain", "--untracked-files=no"],
                               capture_output=True, text=True).stdout.strip()
        return sha + ("-dirty" if dirty else "")
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def loudnorm(src: str | Path, dst: str | Path, lufs: float, tp: float, lra: float = 11.0,
             bitrate: str = "256k") -> dict:
    """Two-pass EBU R128 loudness normalisation; copies the video stream untouched."""
    first = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(src), "-vn",
         "-af", f"loudnorm=I={lufs}:TP={tp}:LRA={lra}:print_format=json", "-f", "null", "-"],
        capture_output=True, text=True, check=True).stderr
    stats = json.loads(first[first.rindex("{"):first.rindex("}") + 1])
    af = (f"loudnorm=I={lufs}:TP={tp}:LRA={lra}:measured_I={stats['input_i']}:measured_TP={stats['input_tp']}"
          f":measured_LRA={stats['input_lra']}:measured_thresh={stats['input_thresh']}"
          f":offset={stats['target_offset']}:linear=true")
    run_ffmpeg(["-i", str(src), "-c:v", "copy", "-af", af, "-ar", "48000", "-c:a", "aac", "-b:a", bitrate,
                "-movflags", "+faststart", str(dst)])
    return {"measured_input_lufs": float(stats["input_i"]), "measured_input_tp": float(stats["input_tp"]),
            "target_lufs": lufs, "target_tp": tp}


def _trim_audio(audio: str | Path, start: float, end: float, out: Path) -> Path:
    run_ffmpeg(["-ss", f"{start:.3f}", "-t", f"{end - start:.3f}", "-i", str(audio), "-vn",
                "-c:a", "pcm_s16le", str(out)])
    return out


class Renderer:
    def __init__(self, project_id: str | None = None, cfg: dict | None = None, out_dir: str | Path | None = None):
        self.project_id = project_id
        self.cfg = cfg or load_config(project_id)
        base = Path(self.cfg["studio"]["renders_dir"])
        self.out_dir = Path(out_dir) if out_dir else (REPO_ROOT / base / (project_id or "scratch"))

    def profile(self, mode: str) -> dict:
        if mode not in self.cfg["render"]:
            raise ValueError(f"Unknown render mode '{mode}'. Use preview or final.")
        return self.cfg["render"][mode]

    def render(self, timeline: Timeline, mode: str = "preview", name: str | None = None,
               start: float = 0.0, end: float | None = None, source_fps: float | None = None,
               progress=None) -> RenderResult:
        prof = self.profile(mode)
        name = name or self.project_id or "untitled"
        end = timeline.duration if end is None else min(end, timeline.duration)
        if prof.get("fps", "source") == "source":
            timeline.fps = source_fps or timeline.fps or self.cfg["render"]["default_fps"]
        else:
            timeline.fps = float(prof["fps"])
        out = versioning.reserve_output(self.out_dir, name, mode)
        t0 = time.time()
        crf = int(prof["crf"])
        audio_info: dict = {}
        with tempfile.TemporaryDirectory(prefix="studio-render-") as tmp:
            tmp = Path(tmp)
            audio = None
            if timeline.audio:
                audio = _trim_audio(timeline.audio, start, end, tmp / "audio.wav") if (start or end < timeline.duration) else timeline.audio
            raw = tmp / "video.mp4"
            timeline.render(raw, prof["width"], prof["height"], start=start, end=end, crf=crf,
                            preset=prof.get("preset", "medium"), audio_path=audio,
                            audio_bitrate=prof.get("audio_bitrate", "192k"), progress=progress)
            if mode == "final" and audio and "loudness_lufs" in prof:
                normed = tmp / "normed.mp4"
                audio_info = loudnorm(raw, normed, prof["loudness_lufs"], prof["true_peak_dbtp"],
                                      bitrate=prof.get("audio_bitrate", "256k"))
                raw = normed
            max_mb = prof.get("max_size_mb")
            while max_mb and raw.stat().st_size / 1e6 > max_mb and crf < 40:
                crf += 3
                smaller = tmp / f"crf{crf}.mp4"
                run_ffmpeg(["-i", str(raw), "-c:v", prof.get("codec", "libx264"), "-crf", str(crf), "-preset",
                            prof.get("preset", "veryfast"), "-c:a", "copy", "-movflags", "+faststart", str(smaller)])
                raw = smaller
            shutil.move(str(raw), out)
        info = probe(out)
        ver = versioning.parse(out)["version"]
        result = RenderResult(
            path=str(out), mode=mode, version=ver, width=info.width, height=info.height, fps=timeline.fps,
            duration=info.duration, size_mb=round(info.size_bytes / 1e6, 3), seconds=round(time.time() - t0, 2),
            range=(start, end), crf=crf, audio=audio_info, git_commit=git_commit(), project_id=self.project_id,
            created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        self._record(result)
        return result

    def _record(self, result: RenderResult) -> None:
        record = asdict(result) | {"host": platform.node(), "user": os.environ.get("USER") or os.environ.get("STUDIO_USER")}
        Path(result.path).with_suffix(".json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        with open(self.out_dir / "renders.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def render_history(out_dir: str | Path) -> list[dict]:
    log = Path(out_dir) / "renders.jsonl"
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]
