"""Auto reframing (e.g. 16:9 interview -> 9:16 vertical) with face tracking and a smooth crop path.

Faces come from OpenCV's bundled Haar cascade (no downloads). Detections are sampled every
`sample_every` seconds, interpolated, then smoothed with a critically-damped follow plus a
dead zone so the virtual camera doesn't jitter on small head movements.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import cv2
import numpy as np

from ..core.io import VideoWriter, probe, read_frames


@dataclass
class CropKey:
    t: float
    cx: float      # crop centre x in source pixels
    cy: float
    w: float       # crop size in source pixels
    h: float


@dataclass
class CropPath:
    source: str
    src_w: int
    src_h: int
    out_w: int
    out_h: int
    fps: float
    keys: list[CropKey] = field(default_factory=list)

    def at(self, t: float) -> CropKey:
        if not self.keys:
            return CropKey(t, self.src_w / 2, self.src_h / 2, *crop_size(self.src_w, self.src_h, self.out_w, self.out_h))
        ts = np.array([k.t for k in self.keys])
        i = int(np.clip(np.searchsorted(ts, t), 1, len(ts) - 1)) if len(ts) > 1 else 0
        if len(ts) == 1:
            return self.keys[0]
        a, b = self.keys[i - 1], self.keys[i]
        p = 0.0 if b.t == a.t else float(np.clip((t - a.t) / (b.t - a.t), 0, 1))
        return CropKey(t, *(getattr(a, f) + (getattr(b, f) - getattr(a, f)) * p for f in ("cx", "cy", "w", "h")))

    def save(self, path: str | Path) -> Path:
        Path(path).write_text(json.dumps(asdict(self), indent=1), encoding="utf-8")
        return Path(path)

    @classmethod
    def load(cls, path: str | Path) -> "CropPath":
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        d["keys"] = [CropKey(**k) for k in d["keys"]]
        return cls(**d)


def crop_size(src_w: int, src_h: int, out_w: int, out_h: int) -> tuple[float, float]:
    """Largest crop of the output aspect ratio that fits inside the source."""
    aspect = out_w / out_h
    if src_w / src_h > aspect:
        return src_h * aspect, float(src_h)
    return float(src_w), src_w / aspect


_CASCADE = None


def detect_faces(img_rgb: np.ndarray, min_size_frac: float = 0.08) -> list[tuple[int, int, int, int]]:
    """Return face boxes (x, y, w, h), largest first."""
    global _CASCADE
    if _CASCADE is None:
        _CASCADE = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    gray = cv2.equalizeHist(cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY))
    ms = int(min(gray.shape) * min_size_frac)
    faces = _CASCADE.detectMultiScale(gray, 1.1, 5, minSize=(ms, ms))
    return sorted((tuple(map(int, f)) for f in faces), key=lambda f: -f[2] * f[3])


def track_faces(path: str | Path, sample_every: float = 0.5, analysis_width: int = 640) -> list[tuple[float, tuple | None]]:
    """[(t, (x, y, w, h) in source px | None)] sampled every `sample_every` seconds."""
    info = probe(path)
    s = analysis_width / info.width
    out = []
    for i, frame in enumerate(read_frames(path, analysis_width, int(info.height * s) // 2 * 2, fps=1 / sample_every)):
        faces = detect_faces(frame)
        t = i * sample_every
        out.append((t, tuple(v / s for v in faces[0]) if faces else None))
    return out


def smooth_path(targets: list[tuple[float, float, float]], dead_zone: float, stiffness: float = 2.5,
                dt: float = 1 / 30) -> list[tuple[float, float, float]]:
    """Critically damped follow of (t, x, y) targets with a dead zone (px). Returns same timestamps."""
    if not targets:
        return []
    out = []
    x, y = targets[0][1], targets[0][2]
    vx = vy = 0.0
    prev_t = targets[0][0]
    for t, tx, ty in targets:
        steps = max(int(round((t - prev_t) / dt)), 1) if out else 1
        for _ in range(steps):
            for axis in (0, 1):
                pos, vel, tgt = (x, vx, tx) if axis == 0 else (y, vy, ty)
                err = tgt - pos
                if abs(err) < dead_zone:
                    err = 0.0
                else:
                    err -= np.sign(err) * dead_zone
                acc = stiffness ** 2 * err - 2 * stiffness * vel
                vel += acc * dt
                pos += vel * dt
                if axis == 0:
                    x, vx = pos, vel
                else:
                    y, vy = pos, vel
        out.append((t, x, y))
        prev_t = t
    return out


def build_crop_path(path: str | Path, out_w: int = 1080, out_h: int = 1920, sample_every: float = 0.5,
                    face_headroom: float = 0.38, dead_zone_frac: float = 0.04, push_in: float = 0.0,
                    detections: list[tuple[float, tuple | None]] | None = None) -> CropPath:
    """Compute the virtual-camera path. `face_headroom` = where the face centre sits vertically in
    the crop (0 top .. 1 bottom); `push_in` = total zoom over the clip (0.06 = 6% slow push)."""
    info = probe(path)
    W, H = info.width, info.height
    cw, ch = crop_size(W, H, out_w, out_h)
    dets = detections if detections is not None else track_faces(path, sample_every)
    # fill gaps: hold last known face, default to frame centre
    targets, last = [], (W / 2, H / 2)
    for t, box in dets:
        if box:
            fx, fy = box[0] + box[2] / 2, box[1] + box[3] / 2
            last = (fx, fy + (0.5 - face_headroom) * ch)
        targets.append((t, *last))
    if not targets:
        targets = [(0.0, W / 2, H / 2)]
    smoothed = smooth_path(targets, dead_zone=dead_zone_frac * cw)
    dur = max(info.duration, 1e-6)
    keys = []
    for t, x, y in smoothed:
        z = 1.0 - push_in * min(t / dur, 1.0)
        w, h = cw * z, ch * z
        keys.append(CropKey(round(t, 3), float(np.clip(x, w / 2, W - w / 2)), float(np.clip(y, h / 2, H - h / 2)),
                            round(w, 2), round(h, 2)))
    return CropPath(str(path), W, H, out_w, out_h, info.fps or 30.0, keys)


def face_in_safe_area(box: tuple, crop: CropKey, safe: dict) -> bool:
    """True if the face box (source px) lies inside the crop's safe area (fractions like config.safe_area)."""
    x0 = crop.cx - crop.w / 2 + crop.w * safe.get("left", 0)
    x1 = crop.cx + crop.w / 2 - crop.w * safe.get("right", 0)
    y0 = crop.cy - crop.h / 2 + crop.h * safe.get("top", 0)
    y1 = crop.cy + crop.h / 2 - crop.h * safe.get("bottom", 0)
    bx, by, bw, bh = box
    return bx >= x0 and by >= y0 and bx + bw <= x1 and by + bh <= y1


def render_reframe(crop_path: CropPath, out: str | Path, crf: int = 18, preset: str = "veryfast",
                   keep_audio: bool = True) -> Path:
    """Apply the crop path frame by frame and encode. Audio is copied from the source."""
    tmp = Path(out).with_suffix(".noaudio.mp4") if keep_audio else Path(out)
    with VideoWriter(tmp, crop_path.out_w, crop_path.out_h, crop_path.fps, crf=crf, preset=preset) as w:
        for i, frame in enumerate(read_frames(crop_path.source)):
            k = crop_path.at(i / crop_path.fps)
            m = np.array([[crop_path.out_w / k.w, 0, -(k.cx - k.w / 2) * crop_path.out_w / k.w],
                          [0, crop_path.out_h / k.h, -(k.cy - k.h / 2) * crop_path.out_h / k.h]], np.float32)
            w.write(cv2.warpAffine(frame, m, (crop_path.out_w, crop_path.out_h), flags=cv2.INTER_LINEAR,
                                   borderMode=cv2.BORDER_REPLICATE))
    if keep_audio:
        from ..core.io import run_ffmpeg
        if probe(crop_path.source).has_audio:
            run_ffmpeg(["-i", str(tmp), "-i", crop_path.source, "-map", "0:v", "-map", "1:a", "-c:v", "copy",
                        "-c:a", "aac", "-b:a", "192k", "-shortest", str(out)])
            tmp.unlink()
        else:
            tmp.rename(out)
    return Path(out)
