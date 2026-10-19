"""Camera motion: whole-frame layers that move a virtual camera over whatever is beneath them.

Put a camera layer *above* the footage it should move (higher z / later in the stack) and below
graphics that should stay locked to the screen.

Face helpers (`detect_faces`, `FaceTracker`, `face_track_path`, `ReframedClipLayer`) use the
OpenCV Haar cascade bundled with opencv-python — no model downloads.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from studio.core import canvas, easing
from studio.core.io import probe, read_frames
from studio.core.timeline import FrameSource, Layer, RenderContext

from ._util import in_expo, smooth_noise


class CameraLayer(Layer):
    """Base: subclasses return (zoom, cx, cy, rotation_deg) where cx/cy are the frame-fraction centre
    the camera looks at (0.5, 0.5 = centre). zoom >= 1 keeps the frame filled."""

    def __init__(self, motion_blur: float = 0.0, **kw):
        super().__init__(**kw)
        self.motion_blur = motion_blur
        self._prev: tuple | None = None

    def camera(self, t: float, ctx: RenderContext) -> tuple[float, float, float, float]:
        return 1.0, 0.5, 0.5, 0.0

    def draw(self, frame, ctx, t):
        zoom, cx, cy, rot = self.camera(t, ctx)
        out = apply_camera(frame, zoom, cx, cy, rot)
        if self.motion_blur > 0 and self._prev is not None:
            pz, pcx, pcy, _ = self._prev
            dx = (cx - pcx) * ctx.width * self.motion_blur
            dy = (cy - pcy) * ctx.height * self.motion_blur
            out = directional_blur(out, dx, dy)
        self._prev = (zoom, cx, cy, rot)
        return out


def apply_camera(frame: np.ndarray, zoom: float, cx: float, cy: float, rotation: float = 0.0) -> np.ndarray:
    """Crop/zoom/rotate `frame` so that (cx, cy) fills the centre at `zoom` (>=1). Centre is clamped
    so the frame never shows empty borders (when rotation is 0)."""
    h, w = frame.shape[:2]
    zoom = max(zoom, 1e-3)
    half_w, half_h = 0.5 / zoom, 0.5 / zoom
    if zoom >= 1:
        cx = min(max(cx, half_w), 1 - half_w)
        cy = min(max(cy, half_h), 1 - half_h)
    if abs(zoom - 1) < 1e-4 and abs(cx - 0.5) < 1e-5 and abs(cy - 0.5) < 1e-5 and abs(rotation) < 1e-4:
        return frame
    m = cv2.getRotationMatrix2D((cx * w, cy * h), rotation, zoom)
    m[0, 2] += w / 2 - cx * w
    m[1, 2] += h / 2 - cy * h
    return cv2.warpAffine(frame, m, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def directional_blur(frame: np.ndarray, dx: float, dy: float) -> np.ndarray:
    length = int(math.hypot(dx, dy))
    if length < 2:
        return frame
    k = np.zeros((length * 2 + 1, length * 2 + 1), np.float32)
    ang = math.atan2(dy, dx)
    cv2.line(k, (length - int(math.cos(ang) * length), length - int(math.sin(ang) * length)),
             (length + int(math.cos(ang) * length), length + int(math.sin(ang) * length)), 1.0, 1)
    k /= max(k.sum(), 1e-6)
    return cv2.filter2D(frame, -1, k, borderType=cv2.BORDER_REFLECT)


class DigitalZoom(CameraLayer):
    """Zoom from `zoom_from` to `zoom_to` over the layer duration around `center`."""

    def __init__(self, zoom_from: float = 1.0, zoom_to: float = 1.3, center=(0.5, 0.5), ease: str = "in_out_cubic", **kw):
        super().__init__(**kw)
        self.zoom_from, self.zoom_to, self.center, self.ease = zoom_from, zoom_to, center, ease

    def camera(self, t, ctx):
        p = easing.progress(t, 0, self.duration or 1.0, self.ease)
        return easing.lerp(self.zoom_from, self.zoom_to, p), self.center[0], self.center[1], 0.0


class SlowPushIn(DigitalZoom):
    def __init__(self, amount: float = 0.08, **kw):
        kw.setdefault("ease", "linear")
        super().__init__(zoom_from=1.0, zoom_to=1.0 + amount, **kw)


class Pan(CameraLayer):
    """Move the look-at point from `start_center` to `end_center` at a fixed zoom."""

    def __init__(self, start_center=(0.35, 0.5), end_center=(0.65, 0.5), zoom: float = 1.25,
                 ease: str = "in_out_sine", **kw):
        super().__init__(**kw)
        self.a, self.b, self.zoom, self.ease = start_center, end_center, zoom, ease

    def camera(self, t, ctx):
        p = easing.progress(t, 0, self.duration or 1.0, self.ease)
        return self.zoom, easing.lerp(self.a[0], self.b[0], p), easing.lerp(self.a[1], self.b[1], p), 0.0


class HandheldDrift(CameraLayer):
    """Organic, deterministic handheld feel: smooth noise on position and a hint of roll."""

    def __init__(self, amplitude: float = 0.012, rotation: float = 0.4, frequency: float = 0.35,
                 zoom: float = 1.06, seed: int = 7, center=(0.5, 0.5), **kw):
        super().__init__(**kw)
        self.amplitude, self.rotation, self.frequency = amplitude, rotation, frequency
        self.zoom, self.seed, self.center = zoom, seed, center

    def camera(self, t, ctx):
        f = self.frequency
        return (self.zoom,
                self.center[0] + self.amplitude * smooth_noise(t, self.seed, freq=f),
                self.center[1] + self.amplitude * smooth_noise(t, self.seed + 1, freq=f),
                self.rotation * smooth_noise(t, self.seed + 2, freq=f * 0.8))


class CameraShake(CameraLayer):
    """Impact shake that decays exponentially. intensity is in frame fractions."""

    def __init__(self, intensity: float = 0.02, frequency: float = 18.0, decay: float = 6.0,
                 rotation: float = 1.5, seed: int = 3, zoom: float = 1.05, **kw):
        super().__init__(**kw)
        self.intensity, self.frequency, self.decay = intensity, frequency, decay
        self.rotation, self.seed, self.zoom = rotation, seed, zoom

    def camera(self, t, ctx):
        env = math.exp(-self.decay * t)
        a = self.intensity * env
        return (self.zoom,
                0.5 + a * smooth_noise(t, self.seed, octaves=2, freq=self.frequency),
                0.5 + a * smooth_noise(t, self.seed + 5, octaves=2, freq=self.frequency),
                self.rotation * env * smooth_noise(t, self.seed + 9, octaves=2, freq=self.frequency * 0.7))


class ZoomThrough(CameraLayer):
    """Accelerating punch-in toward a point, with radial blur ramping up — pair with a cut."""

    def __init__(self, zoom_to: float = 3.0, center=(0.5, 0.5), ease=in_expo, blur: float = 0.6, **kw):
        super().__init__(**kw)
        self.zoom_to, self.center, self.ease, self.blur = zoom_to, center, ease, blur

    def camera(self, t, ctx):
        p = easing.progress(t, 0, self.duration or 0.5, self.ease)
        return easing.lerp(1.0, self.zoom_to, p), self.center[0], self.center[1], 0.0

    def draw(self, frame, ctx, t):
        out = super().draw(frame, ctx, t)
        p = easing.progress(t, 0, self.duration or 0.5, self.ease)
        return radial_blur(out, p * self.blur, self.center)


def radial_blur(frame: np.ndarray, strength: float, center=(0.5, 0.5), samples: int = 6) -> np.ndarray:
    if strength <= 0.01:
        return frame
    acc = frame.copy()
    for i in range(1, samples):
        z = 1 + strength * 0.15 * i / samples
        acc += apply_camera(frame, z, center[0], center[1])
    return acc / samples


class Reframe(CameraLayer):
    """Smoothly reframe between target rects. keyframes = [(t, (x0, y0, x1, y1) frame fractions), ...]."""

    def __init__(self, keyframes: list[tuple[float, tuple[float, float, float, float]]], ease: str = "in_out_cubic", **kw):
        super().__init__(**kw)
        self.keyframes = sorted(keyframes, key=lambda k: k[0])
        self.ease = ease

    @staticmethod
    def _cam(rect):
        x0, y0, x1, y1 = rect
        zoom = 1 / max(x1 - x0, y1 - y0, 1e-3)
        return max(zoom, 1.0), (x0 + x1) / 2, (y0 + y1) / 2

    def camera(self, t, ctx):
        ks = self.keyframes
        if t <= ks[0][0]:
            z, cx, cy = self._cam(ks[0][1])
        elif t >= ks[-1][0]:
            z, cx, cy = self._cam(ks[-1][1])
        else:
            i = next(i for i in range(len(ks) - 1) if ks[i][0] <= t < ks[i + 1][0])
            (t0, r0), (t1, r1) = ks[i], ks[i + 1]
            p = easing.progress(t, t0, t1 - t0, self.ease)
            a, b = self._cam(r0), self._cam(r1)
            z, cx, cy = (easing.lerp(a[j], b[j], p) for j in range(3))
        return z, cx, cy, 0.0


# ---------------- faces ----------------

_CASCADE: cv2.CascadeClassifier | None = None


def _cascade() -> cv2.CascadeClassifier:
    global _CASCADE
    if _CASCADE is None:
        _CASCADE = cv2.CascadeClassifier(str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"))
    return _CASCADE


def detect_faces(frame_uint8: np.ndarray, min_size_frac: float = 0.06, max_width: int = 640) -> list[tuple[int, int, int, int]]:
    """Return face boxes (x, y, w, h) in the input frame's pixel coords, largest first."""
    h, w = frame_uint8.shape[:2]
    s = min(1.0, max_width / w)
    small = cv2.resize(frame_uint8, (int(w * s), int(h * s))) if s < 1 else frame_uint8
    gray = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY)
    gray = cv2.equalizeHist(gray)
    ms = max(int(min(small.shape[:2]) * min_size_frac), 20)
    faces = _cascade().detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(ms, ms))
    boxes = [tuple(int(v / s) for v in f) for f in faces]
    return sorted(boxes, key=lambda b: -b[2] * b[3])


class FaceTracker:
    """Exponential smoothing + dead zone, so the crop doesn't jitter with detector noise."""

    def __init__(self, smoothing: float = 0.85, dead_zone: float = 0.03, hold_frames: int = 30):
        self.smoothing, self.dead_zone, self.hold_frames = smoothing, dead_zone, hold_frames
        self.cx: float | None = None
        self.cy: float | None = None
        self.box: tuple | None = None
        self.missed = 0

    def update(self, box: tuple[float, float, float, float] | None, frame_w: int, frame_h: int) -> tuple[float, float]:
        """Feed a detection (or None); returns smoothed centre in frame fractions."""
        if box is None:
            self.missed += 1
            if self.cx is None or self.missed > self.hold_frames:
                # drift back to centre when the face is lost
                tx, ty = 0.5, 0.45
            else:
                return self.cx, self.cy
        else:
            self.missed = 0
            x, y, w, h = box
            self.box = box
            tx, ty = (x + w / 2) / frame_w, (y + h * 0.45) / frame_h
        if self.cx is None:
            self.cx, self.cy = tx, ty
        else:
            if abs(tx - self.cx) > self.dead_zone or abs(ty - self.cy) > self.dead_zone:
                a = self.smoothing
                self.cx = a * self.cx + (1 - a) * tx
                self.cy = a * self.cy + (1 - a) * ty
        return self.cx, self.cy


@dataclass
class TrackPoint:
    t: float
    cx: float
    cy: float
    face: tuple | None   # (x, y, w, h) frame fractions or None


def face_track_path(path: str | Path, sample_fps: float = 5.0, smoothing: float = 0.6,
                    start: float = 0.0, duration: float | None = None) -> list[TrackPoint]:
    """Sample a video, detect the main face and return a smoothed look-at path."""
    info = probe(path)
    scale_w = min(640, info.width)
    scale_h = int(info.height * scale_w / info.width) // 2 * 2
    tracker = FaceTracker(smoothing=smoothing, hold_frames=int(sample_fps * 2))
    pts = []
    for i, fr in enumerate(read_frames(path, scale_w, scale_h, start=start, duration=duration, fps=sample_fps)):
        faces = detect_faces(fr, max_width=scale_w)
        box = faces[0] if faces else None
        cx, cy = tracker.update(box, scale_w, scale_h)
        frac = None if box is None else (box[0] / scale_w, box[1] / scale_h, box[2] / scale_w, box[3] / scale_h)
        pts.append(TrackPoint(start + i / sample_fps, cx, cy, frac))
    return pts


def crop_window(src_w: int, src_h: int, aspect: float, cx: float, cy: float, zoom: float = 1.0) -> tuple[int, int, int, int]:
    """Largest window of `aspect` (w/h) inside the source, centred on (cx, cy) fractions, clamped."""
    if src_w / src_h > aspect:
        ch = src_h / zoom
        cw = ch * aspect
    else:
        cw = src_w / zoom
        ch = cw / aspect
    x = min(max(cx * src_w - cw / 2, 0), src_w - cw)
    y = min(max(cy * src_h - ch / 2, 0), src_h - ch)
    return int(round(x)), int(round(y)), int(round(cw)), int(round(ch))


def face_in_safe_zone(face: tuple[float, float, float, float], crop: tuple[int, int, int, int],
                      src_w: int, src_h: int, safe: dict) -> bool:
    """True when the face box (fractions of source) lies inside the crop's safe area."""
    fx, fy, fw, fh = face[0] * src_w, face[1] * src_h, face[2] * src_w, face[3] * src_h
    x, y, w, h = crop
    sx0, sy0 = x + w * safe["left"], y + h * safe["top"]
    sx1, sy1 = x + w * (1 - safe["right"]), y + h * (1 - safe["bottom"])
    return fx >= sx0 and fy >= sy0 and fx + fw <= sx1 and fy + fh <= sy1


class ReframedClipLayer(Layer):
    """Auto-crop a (typically 16:9) source to the output aspect, following a face track.

    `track` defaults to face_track_path(path). `zoom` > 1 crops tighter (push-in feel)."""

    def __init__(self, path: str | Path, src_in: float = 0.0, track: list[TrackPoint] | None = None,
                 zoom: float = 1.0, push_in: float = 0.0, **kw):
        super().__init__(**kw)
        self.path, self.src_in, self.zoom, self.push_in = str(path), src_in, zoom, push_in
        self.info = probe(path)
        if self.duration is None:
            self.duration = self.info.duration - src_in
        self.track = track if track is not None else face_track_path(path, start=src_in, duration=self.duration)
        self._src: FrameSource | None = None

    def centre_at(self, src_t: float) -> tuple[float, float]:
        if not self.track:
            return 0.5, 0.5
        ts = np.array([p.t for p in self.track])
        return float(np.interp(src_t, ts, [p.cx for p in self.track])), float(np.interp(src_t, ts, [p.cy for p in self.track]))

    def draw(self, frame, ctx, t):
        if self._src is None:
            self._src = FrameSource(self.path, self.info.width, self.info.height)
        src_t = self.src_in + t
        img = self._src.frame_at(src_t)
        cx, cy = self.centre_at(src_t)
        z = self.zoom + self.push_in * (t / max(self.duration, 1e-6))
        x, y, w, h = crop_window(self.info.width, self.info.height, ctx.width / ctx.height, cx, cy, z)
        crop = cv2.resize(img[y:y + h, x:x + w], (ctx.width, ctx.height),
                          interpolation=cv2.INTER_AREA if w > ctx.width else cv2.INTER_LINEAR)
        frame[:] = frame * (1 - self.opacity) + canvas.from_uint8(crop) * self.opacity
        return frame
