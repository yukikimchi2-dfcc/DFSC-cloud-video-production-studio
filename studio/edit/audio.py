"""Audio engine built on ffmpeg filters: cleanup chain, loudness normalisation, ducking, mixing.

Loudness targets default to config render.final (-14 LUFS integrated, -1.5 dBTP).
`normalize_loudness` uses the two-pass loudnorm method (measure, then apply linear gain).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from ..config import get, load_config
from ..core.io import probe, run_ffmpeg

_AUDIO_CODEC = {".wav": ["-c:a", "pcm_s16le"], ".flac": ["-c:a", "flac"]}


def _codec_args(out: str | Path, bitrate: str = "256k") -> list[str]:
    return _AUDIO_CODEC.get(Path(out).suffix.lower(), ["-c:a", "aac", "-b:a", bitrate])


def _output_args(src: str | Path, out: str | Path, bitrate: str) -> list[str]:
    """Copy video untouched if both input and output are video containers."""
    if Path(out).suffix.lower() in (".mp4", ".mov", ".mkv") and probe(src).has_video:
        return ["-map", "0:v?", "-map", "[aout]", "-c:v", "copy", *_codec_args(out, bitrate)]
    return ["-map", "[aout]", "-vn", *_codec_args(out, bitrate)]


@dataclass
class Loudness:
    integrated_lufs: float
    true_peak_dbtp: float
    lra: float
    threshold: float

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def _parse_loudnorm(stderr: str) -> dict:
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", stderr, re.S)
    if not m:
        raise RuntimeError("loudnorm produced no measurement (is there an audio stream?)")
    return json.loads(m.group(0))


def measure_loudness(path: str | Path, target_lufs: float = -14.0, target_tp: float = -1.5) -> Loudness:
    """EBU R128 measurement via ffmpeg loudnorm (print_format=json)."""
    proc = run_ffmpeg(["-hide_banner", "-v", "info", "-i", str(path), "-vn",
                       "-af", f"loudnorm=I={target_lufs}:TP={target_tp}:LRA=11:print_format=json", "-f", "null", "-"])
    d = _parse_loudnorm(proc.stderr)
    f = lambda k: float(d[k]) if d[k] not in ("-inf", "inf") else float("-inf")  # noqa: E731
    return Loudness(f("input_i"), f("input_tp"), f("input_lra"), f("input_thresh"))


def measure_peak(path: str | Path) -> float:
    """Sample peak in dBFS (astats)."""
    proc = run_ffmpeg(["-hide_banner", "-v", "info", "-i", str(path), "-vn", "-af", "astats=measure_perchannel=none",
                       "-f", "null", "-"])
    vals = re.findall(r"Peak level dB:\s*(-?[\d.]+|-inf)", proc.stderr)
    return max((float(v) if v != "-inf" else float("-inf")) for v in vals) if vals else float("-inf")


def cleanup_filter(denoise: float = 12.0, highpass: int = 80, presence_db: float = 2.0, deess: bool = True,
                   compress: bool = True) -> str:
    """Voice cleanup chain: high-pass, FFT denoise, presence EQ, gentle de-ess, compression."""
    parts = [f"highpass=f={highpass}"]
    if denoise > 0:
        parts.append(f"afftdn=nr={denoise}:nf=-50")
    if presence_db:
        parts.append(f"equalizer=f=3500:t=q:w=1.2:g={presence_db}")
        parts.append("equalizer=f=250:t=q:w=1.0:g=-1.5")      # reduce boxiness
    if deess:
        parts.append("equalizer=f=7000:t=q:w=2:g=-2")
    if compress:
        parts.append("acompressor=threshold=-20dB:ratio=3:attack=10:release=150:makeup=2")
    return ",".join(parts)


def clean_voice(src: str | Path, out: str | Path, bitrate: str = "256k", **filter_kw) -> Path:
    run_ffmpeg(["-i", str(src), "-filter_complex", f"[0:a]{cleanup_filter(**filter_kw)}[aout]",
                *_output_args(src, out, bitrate), str(out)])
    return Path(out)


def normalize_loudness(src: str | Path, out: str | Path, target_lufs: float | None = None,
                       target_tp: float | None = None, cfg: dict | None = None, bitrate: str = "256k") -> Loudness:
    """Two-pass loudnorm to target LUFS / true peak. Returns the measurement of the *output*."""
    cfg = cfg or load_config()
    target_lufs = target_lufs if target_lufs is not None else get(cfg, "render.final.loudness_lufs", -14.0)
    target_tp = target_tp if target_tp is not None else get(cfg, "render.final.true_peak_dbtp", -1.5)
    proc = run_ffmpeg(["-hide_banner", "-v", "info", "-i", str(src), "-vn",
                       "-af", f"loudnorm=I={target_lufs}:TP={target_tp}:LRA=11:print_format=json", "-f", "null", "-"])
    m = _parse_loudnorm(proc.stderr)
    af = (f"loudnorm=I={target_lufs}:TP={target_tp}:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
          f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:"
          f"linear=true,aresample=48000")
    run_ffmpeg(["-i", str(src), "-filter_complex", f"[0:a]{af}[aout]", *_output_args(src, out, bitrate), str(out)])
    return measure_loudness(out, target_lufs, target_tp)


def duck_music(voice: str | Path, music: str | Path, out: str | Path, music_gain_db: float = -8.0,
               duck_db: float = 12.0, attack_ms: int = 30, release_ms: int = 400, bitrate: str = "256k") -> Path:
    """Mix music under voice, ducking it by up to `duck_db` whenever speech is present."""
    ratio = max(2.0, min(20.0, 10 ** (duck_db / 20)))
    fc = (f"[1:a]volume={music_gain_db}dB,aresample=48000[m];[0:a]aresample=48000,asplit=2[v][sc];"
          f"[m][sc]sidechaincompress=threshold=0.03:ratio={ratio:.2f}:attack={attack_ms}:release={release_ms}[md];"
          f"[v][md]amix=inputs=2:duration=first:normalize=0[aout]")
    run_ffmpeg(["-i", str(voice), "-i", str(music), "-filter_complex", fc, *_output_args(voice, out, bitrate), str(out)])
    return Path(out)


def crossfade(a: str | Path, b: str | Path, out: str | Path, duration: float = 0.5, bitrate: str = "256k") -> Path:
    run_ffmpeg(["-i", str(a), "-i", str(b), "-filter_complex",
                f"[0:a][1:a]acrossfade=d={duration}:c1=tri:c2=tri[aout]", "-map", "[aout]", *_codec_args(out, bitrate), str(out)])
    return Path(out)


def place_sfx(base: str | Path, sfx: list[tuple[str | Path, float, float]], out: str | Path,
              bitrate: str = "256k") -> Path:
    """Overlay sound effects: sfx = [(path, at_seconds, gain_db), ...]. Base length is kept."""
    args = ["-i", str(base)]
    chains, labels = [], ["[0:a]"]
    for i, (path, at, gain) in enumerate(sfx, 1):
        args += ["-i", str(path)]
        ms = int(at * 1000)
        chains.append(f"[{i}:a]volume={gain}dB,adelay={ms}|{ms},aresample=48000[s{i}]")
        labels.append(f"[s{i}]")
    chains.append("".join(labels) + f"amix=inputs={len(labels)}:duration=first:normalize=0[aout]")
    run_ffmpeg(args + ["-filter_complex", ";".join(chains), *_output_args(base, out, bitrate), str(out)])
    return Path(out)
