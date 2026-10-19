"""Speech cleaning: pause/filler removal with click-free cuts, rendering, and post-cut verification.

Pause detection is energy based, so it works without any ASR model. Filler removal uses
Word.is_filler from a Transcript. Cut points are snapped to the quietest spot near the
requested time, then to the nearest zero crossing.
"""
from __future__ import annotations

import difflib
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..core.io import probe, read_audio, run_ffmpeg
from .segments import EDL, EDLEvent
from .transcribe import Transcript

SR = 16000


def frame_energy_db(audio: np.ndarray, sr: int = SR, hop: float = 0.01) -> tuple[np.ndarray, float]:
    """RMS energy in dBFS per `hop`-second frame of a mono signal."""
    n = max(int(sr * hop), 1)
    frames = len(audio) // n
    if frames == 0:
        return np.array([-120.0]), hop
    rms = np.sqrt(np.mean(audio[:frames * n].reshape(frames, n) ** 2, axis=1))
    return 20 * np.log10(rms + 1e-9), hop


def detect_silences(path: str | Path, threshold_db: float = -40.0, min_silence: float = 0.35,
                    audio: np.ndarray | None = None) -> list[tuple[float, float]]:
    """Return [(start, end)] of regions quieter than `threshold_db` lasting >= `min_silence` s."""
    if audio is None:
        audio = read_audio(path, SR, mono=True)[:, 0]
    db, hop = frame_energy_db(audio)
    quiet = db < threshold_db
    out, start = [], None
    for i, q in enumerate(np.append(quiet, False)):
        if q and start is None:
            start = i
        elif not q and start is not None:
            if (i - start) * hop >= min_silence:
                out.append((start * hop, i * hop))
            start = None
    return out


def snap_cut(audio: np.ndarray, t: float, sr: int = SR, search: float = 0.06) -> float:
    """Move `t` to the lowest-energy 5 ms window within ±search, then to a zero crossing."""
    lo, hi = max(int((t - search) * sr), 0), min(int((t + search) * sr), len(audio) - 1)
    if hi - lo < 4:
        return t
    seg = audio[lo:hi]
    win = max(int(0.005 * sr), 1)
    energy = np.convolve(seg ** 2, np.ones(win), "same")
    idx = lo + int(np.argmin(energy))
    zc = np.where(np.diff(np.signbit(audio[max(idx - win, 0):idx + win])))[0]
    if len(zc):
        idx = max(idx - win, 0) + int(zc[np.argmin(np.abs(zc - win))])
    return idx / sr


@dataclass
class CutPlan:
    keep: list[tuple[float, float]]
    removed: list[tuple[float, float, str]]   # (start, end, reason)

    @property
    def kept_duration(self) -> float:
        return sum(b - a for a, b in self.keep)


def plan_cuts(path: str | Path, transcript: Transcript | None = None, remove_fillers: bool = True,
              max_pause: float = 0.5, keep_pause: float = 0.15, threshold_db: float = -40.0) -> CutPlan:
    """Decide which source ranges to keep. Pauses longer than `max_pause` shrink to `keep_pause`;
    filler words are removed. Returned ranges are snapped to quiet zero crossings."""
    audio = read_audio(path, SR, mono=True)[:, 0]
    duration = len(audio) / SR
    remove: list[tuple[float, float, str]] = []
    for a, b in detect_silences(path, threshold_db, max_pause, audio=audio):
        half = keep_pause / 2
        if b - a > keep_pause:
            remove.append((a + half, b - half, "pause"))
    if transcript and remove_fillers:
        for w in transcript.words:
            if w.is_filler:
                remove.append((w.start, w.end, f"filler:{w.text.strip()}"))
    remove.sort()
    merged: list[list] = []
    for a, b, why in remove:
        if merged and a <= merged[-1][1] + 0.02:
            merged[-1][1] = max(merged[-1][1], b)
            merged[-1][2] += "+" + why
        else:
            merged.append([a, b, why])
    keep, cursor = [], 0.0
    for a, b, _ in merged:
        a, b = snap_cut(audio, a), snap_cut(audio, b)
        if a - cursor > 0.04:
            keep.append((round(cursor, 4), round(a, 4)))
        cursor = max(cursor, b)
    if duration - cursor > 0.04:
        keep.append((round(cursor, 4), round(duration, 4)))
    return CutPlan(keep, [(round(a, 4), round(b, 4), w) for a, b, w in merged])


def plan_to_edl(plan: CutPlan, source: str, title: str = "clean", fps: float = 30.0) -> EDL:
    edl = EDL(title, fps, [EDLEvent(0, "Clean", str(source), a, b, "", 1.0) for a, b in plan.keep])
    edl.relink()
    return edl


def render_cut(edl: EDL, out: str | Path, fade: float = 0.012, audio_only: bool | None = None,
               crf: int = 18, preset: str = "veryfast") -> Path:
    """Concatenate EDL events (any number of sources) with ffmpeg.

    Video renders keep A/V sync by applying `fade`-second fades at each cut (click-free).
    Audio-only renders use true overlapping crossfades (acrossfade)."""
    sources = list(dict.fromkeys(e.source for e in edl.events))
    if not edl.events:
        raise ValueError("EDL has no events")
    info = probe(sources[0])
    if audio_only is None:
        audio_only = not info.has_video
    args: list[str] = []
    for s in sources:
        args += ["-i", s]
    chains, labels = [], []
    for i, e in enumerate(edl.events):
        si = sources.index(e.source)
        d = e.src_out - e.src_in
        f = min(fade, d / 4)
        a = (f"[{si}:a]atrim={e.src_in:.4f}:{e.src_out:.4f},asetpts=PTS-STARTPTS,"
             f"afade=t=in:d={f:.4f},afade=t=out:st={d - f:.4f}:d={f:.4f}[a{i}]")
        chains.append(a)
        if not audio_only:
            chains.append(f"[{si}:v]trim={e.src_in:.4f}:{e.src_out:.4f},setpts=PTS-STARTPTS[v{i}]")
            labels.append(f"[v{i}][a{i}]")
        else:
            labels.append(f"[a{i}]")
    n = len(edl.events)
    if audio_only:
        if n == 1:
            chains.append("[a0]anull[aout]")
        else:
            prev = "a0"
            for i in range(1, n):
                nxt = "aout" if i == n - 1 else f"x{i}"
                chains.append(f"[{prev}][a{i}]acrossfade=d={fade * 2:.4f}:c1=tri:c2=tri[{nxt}]")
                prev = nxt
        args += ["-filter_complex", ";".join(chains), "-map", "[aout]", "-c:a", "pcm_s16le" if str(out).endswith(".wav") else "aac"]
    else:
        chains.append("".join(labels) + f"concat=n={n}:v=1:a=1[vout][aout]")
        args += ["-filter_complex", ";".join(chains), "-map", "[vout]", "-map", "[aout]",
                 "-c:v", "libx264", "-crf", str(crf), "-preset", preset, "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k"]
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(args + [str(out)])
    return Path(out)


@dataclass
class CutVerification:
    ok: bool
    missing: list[str]       # words present before the cut but not after (excluding fillers)
    added: list[str]
    similarity: float

    def summary(self) -> str:
        return (f"similarity={self.similarity:.3f} missing={len(self.missing)} added={len(self.added)}"
                + (f" — missing: {'、'.join(self.missing[:10])}" if self.missing else ""))


def verify_cut(original: Transcript, new: Transcript, tolerance: int = 0) -> CutVerification:
    """Compare the re-transcription of a cut against the original (fillers ignored)."""
    a = [w.text.strip() for w in original.words if not w.is_filler and w.text.strip()]
    b = [w.text.strip() for w in new.words if not w.is_filler and w.text.strip()]
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    missing, added = [], []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op in ("delete", "replace"):
            missing += a[i1:i2]
        if op in ("insert", "replace"):
            added += b[j1:j2]
    return CutVerification(len(missing) <= tolerance, missing, added, round(sm.ratio(), 4))
