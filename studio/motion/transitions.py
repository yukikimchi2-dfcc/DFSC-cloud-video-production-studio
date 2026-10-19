"""Transitions between two sources. All durations are in FRAMES.

    seq = SequenceLayer([clip_a, clip_b, clip_c],
                        [Transition("whip_pan", 8), Transition("star", 14)], fps=30)

`blend(a, b, p, kind)` is the pure function underneath: p=0 returns A exactly, p=1 returns B exactly.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import cv2
import numpy as np

from studio.core import easing
from studio.core.timeline import Layer, RenderContext

from ._util import in_expo
from .camera import apply_camera, directional_blur

KINDS = ("cut", "dissolve", "zoom_through", "motion_blur", "whip_pan", "flash", "wipe", "circle", "star", "match_cut")


def _star_polys(ctx_brand, w: int, h: int, p: float, rotation: float) -> list[np.ndarray]:
    """Star polygon(s) in frame px sized so that p=1 fully covers the frame."""
    diag = math.hypot(w, h)
    shape = None
    if ctx_brand is not None and "north_star_black" in getattr(ctx_brand, "logos", {}):
        try:
            shape = ctx_brand.logo_shape("north_star_black")
        except Exception:
            shape = None
    if shape is None:
        from studio.core.vector import star_shape
        shape = star_shape(4, 1.0, 0.3)
    vw, vh = shape["viewbox"]
    pts = [np.asarray(sp, np.float64) - [vw / 2, vh / 2] for path in shape["paths"] for sp in path["subpaths"]]
    # the star's concave corners sit ~0.25 of the box from centre: cover diag with margin
    size = easing.in_cubic(p) * diag / 0.42
    s = size / max(vw, vh)
    a = math.radians(rotation)
    rot = np.array([[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]])
    return [np.round((pp * s) @ rot.T + [w / 2, h / 2]).astype(np.int32) for pp in pts]


def blend(a: np.ndarray, b: np.ndarray, p: float, kind: str = "dissolve", direction: str = "left",
          flash_color=(1.0, 1.0, 1.0), brand=None) -> np.ndarray:
    if kind not in KINDS:
        raise ValueError(f"Unknown transition '{kind}'. Available: {KINDS}")
    if p <= 0:
        return a
    if p >= 1:
        return b
    h, w = a.shape[:2]
    if kind == "cut":
        return a if p < 0.5 else b
    if kind == "dissolve":
        q = easing.in_out_sine(p)
        return a * (1 - q) + b * q
    if kind == "zoom_through":
        # A punches in, B arrives from a slightly larger scale; quick crossfade in the middle
        q = easing.in_out_cubic(p)
        za = apply_camera(a, 1 + 1.5 * in_expo(min(p * 2, 1)), 0.5, 0.5)
        zb = apply_camera(b, 1 + 0.6 * (1 - easing.out_expo(max(p * 2 - 1, 0))), 0.5, 0.5)
        mix = easing.clamp01((p - 0.35) / 0.3)
        out = za * (1 - mix) + zb * mix
        blur = (1 - abs(2 * p - 1)) * 0.06 * w
        return directional_blur(out, 0, blur * 0.3) if blur > 2 else out
    if kind == "motion_blur":
        q = easing.in_out_sine(p)
        amt = math.sin(math.pi * p) * 0.05 * w
        return directional_blur(a * (1 - q) + b * q, amt, 0)
    if kind == "whip_pan":
        sign = -1 if direction == "left" else 1
        q = easing.in_out_expo(p)
        shift = int(round(q * w))
        out = np.empty_like(a)
        # A leaves, B enters from the opposite side
        if sign < 0:
            out[:, :w - shift] = a[:, shift:]
            out[:, w - shift:] = b[:, :shift]
        else:
            out[:, shift:] = a[:, :w - shift]
            out[:, :shift] = b[:, w - shift:]
        blur = math.sin(math.pi * p) * 0.12 * w
        return directional_blur(out, blur, 0)
    if kind == "flash":
        base = a if p < 0.5 else b
        f = 1 - abs(2 * p - 1)          # peaks at the cut
        f = f ** 1.5
        return base * (1 - f) + np.array(flash_color, np.float32) * f
    if kind == "match_cut":
        base = a if p < 0.5 else b
        f = max(0.0, 1 - abs(p - 0.5) * 8)  # very short flash right at the cut
        return base * (1 - f * 0.7) + np.array(flash_color, np.float32) * f * 0.7
    # mask reveals
    q = easing.in_out_cubic(p)
    if kind == "wipe":
        soft = max(w * 0.02, 2)
        xs = np.arange(w, dtype=np.float32)
        ys = np.arange(h, dtype=np.float32)
        if direction in ("left", "right"):
            edge = q * (w + soft) - soft / 2
            m = np.clip((edge - (xs if direction == "left" else w - 1 - xs)) / soft + 0.5, 0, 1)[None, :, None]
        else:
            edge = q * (h + soft) - soft / 2
            m = np.clip((edge - (ys if direction == "down" else h - 1 - ys)) / soft + 0.5, 0, 1)[:, None, None]
    elif kind == "circle":
        mm = np.zeros((h, w), np.uint8)
        r = int(q * math.hypot(w, h) / 2) + 1
        cv2.circle(mm, (w // 2, h // 2), r, 255, -1, lineType=cv2.LINE_AA)
        m = (mm.astype(np.float32) / 255)[..., None]
    else:  # star
        mm = np.zeros((h, w), np.uint8)
        cv2.fillPoly(mm, _star_polys(brand, w, h, p, rotation=90 * (1 - q)), 255, lineType=cv2.LINE_AA)
        m = (mm.astype(np.float32) / 255)[..., None]
    return a * (1 - m) + b * m


@dataclass
class Transition:
    kind: str = "dissolve"
    frames: int = 12
    options: dict = field(default_factory=dict)


def render_layer(layer: Layer, base: np.ndarray, ctx: RenderContext, t_local: float) -> np.ndarray:
    """Render one layer standalone on a copy of `base`."""
    return layer.draw(base.copy(), ctx, t_local)


class TransitionLayer(Layer):
    """Blend source layer A into B over `frames` frames. A is drawn at a_in + t, B at b_in + t."""

    def __init__(self, a: Layer, b: Layer, frames: int = 12, kind: str = "dissolve", fps: float = 30.0,
                 a_in: float = 0.0, b_in: float = 0.0, options: dict | None = None, **kw):
        kw.setdefault("duration", frames / fps)
        super().__init__(**kw)
        self.a, self.b, self.frames, self.kind, self.fps = a, b, frames, kind, fps
        self.a_in, self.b_in, self.options = a_in, b_in, options or {}

    def progress(self, t: float) -> float:
        # frame-exact: frame 0 -> 0.0, last frame -> 1.0
        n = max(self.frames - 1, 1)
        return min(max(round(t * self.fps) / n, 0.0), 1.0)

    def draw(self, frame, ctx, t):
        p = self.progress(t)
        fa = render_layer(self.a, frame, ctx, self.a_in + t) if p < 1 else None
        fb = render_layer(self.b, frame, ctx, self.b_in + t) if p > 0 else None
        if fa is None:
            return fb
        if fb is None:
            return fa
        return blend(fa, fb, p, self.kind, brand=ctx.brand, **self.options).astype(np.float32)


class SequenceLayer(Layer):
    """Plays layers back to back; each Transition overlaps the end of one with the start of the next."""

    def __init__(self, segments: list[Layer], transitions: list[Transition | None] | None = None,
                 fps: float = 30.0, **kw):
        transitions = list(transitions or [])
        transitions += [None] * (len(segments) - 1 - len(transitions))
        self.segments, self.transitions, self.fps = segments, transitions, fps
        self.starts: list[float] = []
        t = 0.0
        for i, seg in enumerate(segments):
            if seg.duration is None:
                raise ValueError(f"segment {i} ({seg.name}) needs a duration")
            self.starts.append(t)
            tr = transitions[i] if i < len(transitions) else None
            overlap = (tr.frames / fps) if (tr and tr.kind != "cut") else 0.0
            t += seg.duration - overlap
        kw.setdefault("duration", self.starts[-1] + segments[-1].duration if segments else 0.0)
        super().__init__(**kw)

    def draw(self, frame, ctx, t):
        for i, (seg, s) in enumerate(zip(self.segments, self.starts)):
            e = s + seg.duration
            if not (s <= t < e):
                continue
            tr = self.transitions[i] if i < len(self.transitions) else None
            if tr and tr.kind != "cut" and i + 1 < len(self.segments) and t >= self.starts[i + 1]:
                nxt, ns = self.segments[i + 1], self.starts[i + 1]
                n = max(tr.frames - 1, 1)
                p = min(max(round((t - ns) * self.fps) / n, 0.0), 1.0)
                fa = render_layer(seg, frame, ctx, t - s)
                fb = render_layer(nxt, frame, ctx, t - ns)
                return blend(fa, fb, p, tr.kind, brand=ctx.brand, **tr.options).astype(np.float32)
            return render_layer(seg, frame, ctx, t - s)
        return frame


class GroupLayer(Layer):
    """A stack of layers treated as one (e.g. a sequence segment: footage + camera + graphics).
    Children use times local to the group."""

    def __init__(self, layers: list[Layer], background=None, **kw):
        super().__init__(**kw)
        self.layers = layers
        self.background = background

    def draw(self, frame, ctx, t):
        if self.background is not None:
            from studio.core.canvas import hex_to_rgb
            frame = frame.copy()
            frame[:] = hex_to_rgb(self.background) if isinstance(self.background, str) else self.background
        for layer in sorted(self.layers, key=lambda l: l.z):
            if layer.active(t):
                frame = layer.draw(frame, ctx, t - layer.start)
        return frame
