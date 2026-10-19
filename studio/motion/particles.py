"""Particles and frame effects. Everything is deterministic (seeded) and seekable: a particle's
state is computed analytically from time, so any frame can be rendered in any order."""
from __future__ import annotations

import functools
import math

import cv2
import numpy as np

from studio.core import canvas, easing, vector
from studio.core.canvas import Patch
from studio.core.timeline import Layer, RenderContext

from ._util import resolve_color, smooth_noise


@functools.lru_cache(maxsize=64)
def _sprite(kind: str, size: int, rgb: tuple, soft: float = 0.0) -> np.ndarray:
    """Cached RGBA sprite: 'star' (4-point), 'dot' (soft disc), 'ring'."""
    size = max(size, 2)
    if kind == "star":
        rgba = vector.render_shape(vector.star_shape(4, 1.0, 0.18, rotation_deg=0), size).rgba
        rgba[..., :3] = rgb
    else:
        ys, xs = np.mgrid[0:size, 0:size].astype(np.float32)
        r = np.hypot(xs - (size - 1) / 2, ys - (size - 1) / 2) / (size / 2)
        if kind == "ring":
            a = np.clip(1 - np.abs(r - 0.8) / 0.12, 0, 1)
        else:
            a = np.clip(1 - r, 0, 1) ** (1 + soft * 3) if soft else np.clip((1 - r) * size / 2, 0, 1)
        rgba = np.dstack([np.broadcast_to(np.array(rgb, np.float32), (size, size, 3)), a]).astype(np.float32)
    return rgba


class _SpriteField(Layer):
    """Base for layers that stamp many sprites per frame onto a frame-sized overlay."""

    blend_mode = "add"

    def stamps(self, ctx: RenderContext, t: float):  # yields (kind, size_px, rgb, x, y, alpha)
        return []

    def draw(self, frame, ctx, t):
        for kind, size, rgb, x, y, alpha, soft in self.stamps(ctx, t):
            if alpha <= 0.003 or size < 2:
                continue
            spr = _sprite(kind, int(size), tuple(round(c, 3) for c in rgb), soft)
            p = Patch(spr, int(x - spr.shape[1] / 2), int(y - spr.shape[0] / 2))
            canvas.composite(frame, p, alpha * self.opacity, self.blend_mode)
        return frame


class StarSparkles(_SpriteField):
    """Twinkling 4-point stars at seeded positions inside `region` (design px x0, y0, x1, y1)."""

    blend_mode = "normal"

    def __init__(self, count: int = 24, region=(0, 0, 1080, 1920), size_range=(18, 60), color="#FFFFFF",
                 twinkle_speed: float = 1.2, seed: int = 11, **kw):
        super().__init__(**kw)
        rng = np.random.default_rng(seed)
        x0, y0, x1, y1 = region
        self.pos = np.stack([rng.uniform(x0, x1, count), rng.uniform(y0, y1, count)], 1)
        self.sizes = rng.uniform(*size_range, count)
        self.phase = rng.uniform(0, 2 * math.pi, count)
        self.speed = rng.uniform(0.6, 1.4, count) * twinkle_speed
        self.color = color

    def stamps(self, ctx, t):
        rgb = resolve_color(ctx.brand, self.color)
        fade_in = easing.progress(t, 0, 0.4, "out_cubic")
        for (x, y), s, ph, sp in zip(self.pos, self.sizes, self.phase, self.speed):
            tw = 0.5 + 0.5 * math.sin(2 * math.pi * sp * t + ph)
            yield "star", ctx.px(s * (0.35 + 0.65 * tw)), rgb, ctx.px(x), ctx.px(y), fade_in * (0.3 + 0.7 * tw), 0.0


class LightDots(_SpriteField):
    """Soft bokeh dots drifting upward with gentle sway (additive)."""

    def __init__(self, count: int = 30, size_range=(10, 46), color="#FFFFFF", speed: float = 60.0,
                 intensity: float = 0.35, seed: int = 5, **kw):
        super().__init__(**kw)
        rng = np.random.default_rng(seed)
        self.x = rng.uniform(0, 1080, count)
        self.y0 = rng.uniform(0, 1920, count)
        self.sizes = rng.uniform(*size_range, count)
        self.speeds = rng.uniform(0.5, 1.5, count) * speed
        self.seeds = rng.integers(0, 10_000, count)
        self.color, self.intensity = color, intensity

    def stamps(self, ctx, t):
        rgb = resolve_color(ctx.brand, self.color)
        for x, y0, s, v, sd in zip(self.x, self.y0, self.sizes, self.speeds, self.seeds):
            y = (y0 - v * t) % 2000 - 40
            xx = x + 30 * smooth_noise(t, int(sd), octaves=2, freq=0.2)
            yield "dot", ctx.px(s), rgb, ctx.px(xx), ctx.px(y), self.intensity, 0.8


class ParticleEmitter(_SpriteField):
    """Burst / stream emitter. Particle i spawns at i / rate; position is integrated analytically.

    origin, velocity and gravity are in design px (per second / per second^2)."""

    def __init__(self, origin=(540, 960), rate: float = 40.0, burst: int = 0, lifetime: float = 1.6,
                 speed=(250, 650), angle=(0, 360), gravity: float = 400.0, drag: float = 0.6,
                 size=(10, 34), color="#FFFFFF", colors: list | None = None, shape: str = "star",
                 emit_duration: float | None = None, seed: int = 1, blend: str = "normal", **kw):
        super().__init__(**kw)
        self.origin, self.rate, self.burst, self.lifetime = origin, rate, burst, lifetime
        self.speed, self.angle, self.gravity, self.drag = speed, angle, gravity, drag
        self.size, self.colors, self.shape, self.seed = size, colors or [color], shape, seed
        self.emit_duration = emit_duration if emit_duration is not None else (self.duration or 1.0)
        self.blend_mode = blend
        n = burst + int(rate * self.emit_duration)
        rng = np.random.default_rng(seed)
        self.spawn = np.concatenate([np.zeros(burst), np.arange(n - burst) / max(rate, 1e-6)])
        ang = np.radians(rng.uniform(*angle, n))
        sp = rng.uniform(*speed, n)
        self.v = np.stack([np.cos(ang) * sp, -np.sin(ang) * sp], 1)
        self.sz = rng.uniform(*size, n)
        self.col = rng.integers(0, len(self.colors), n)
        self.life = lifetime * rng.uniform(0.7, 1.0, n)

    def stamps(self, ctx, t):
        rgbs = [resolve_color(ctx.brand, c) for c in self.colors]
        k = self.drag
        for i in np.nonzero((self.spawn <= t) & (t < self.spawn + self.life))[0]:
            age = t - self.spawn[i]
            # velocity with linear drag: v e^{-kt};  integral = v (1 - e^{-kt}) / k
            f = (1 - math.exp(-k * age)) / k if k > 0 else age
            x = self.origin[0] + self.v[i, 0] * f
            y = self.origin[1] + self.v[i, 1] * f + 0.5 * self.gravity * age * age
            life_p = age / self.life[i]
            alpha = min(1.0, (1 - life_p) * 2.5) * min(1.0, age * 12)
            yield self.shape, ctx.px(self.sz[i] * (1 - 0.5 * life_p)), rgbs[self.col[i]], ctx.px(x), ctx.px(y), alpha, 0.0


class ShapeLayer(Layer):
    """Simple animated vector shape: 'circle', 'ring', 'rect', 'line', 'star' with keyframed
    position/scale/rotation/opacity. keyframes = {"scale": [(t, v), ...], "x": [...], ...}."""

    def __init__(self, shape: str = "circle", x: float = 540, y: float = 960, size: float = 200,
                 color="accent", thickness: float = 8, keyframes: dict | None = None, ease: str = "out_cubic", **kw):
        super().__init__(**kw)
        self.shape, self.x, self.y, self.size, self.color = shape, x, y, size, color
        self.thickness, self.keyframes, self.ease = thickness, keyframes or {}, ease

    def _kf(self, name: str, t: float, default: float) -> float:
        ks = self.keyframes.get(name)
        if not ks:
            return default
        if t <= ks[0][0]:
            return ks[0][1]
        for (t0, v0), (t1, v1) in zip(ks, ks[1:]):
            if t0 <= t < t1:
                return easing.lerp(v0, v1, easing.progress(t, t0, t1 - t0, self.ease))
        return ks[-1][1]

    def render(self, ctx, t):
        s = self._kf("scale", t, 1.0)
        op = self._kf("opacity", t, 1.0)
        if s <= 0.01 or op <= 0.003:
            return None
        size = max(ctx.px(self.size * s), 2)
        rgb = resolve_color(ctx.brand, self.color)
        th = max(int(self.thickness * ctx.scale), 1)
        if self.shape in ("circle", "ring", "rect", "line"):
            ss = 4
            m = np.zeros((size * ss, size * ss), np.uint8)
            c = size * ss // 2
            if self.shape == "circle":
                cv2.circle(m, (c, c), c - 1, 255, -1)
            elif self.shape == "ring":
                cv2.circle(m, (c, c), c - th * ss // 2 - 1, 255, th * ss)
            elif self.shape == "rect":
                m[:] = 255
            else:
                m[c - th * ss // 2:c + th * ss // 2 + 1] = 255
            a = cv2.resize(m, (size, size), interpolation=cv2.INTER_AREA).astype(np.float32) / 255
            rgba = np.dstack([np.broadcast_to(np.array(rgb, np.float32), (size, size, 3)), a]).astype(np.float32)
        else:
            rgba = vector.render_shape(vector.star_shape(), size).rgba
            rgba[..., :3] = rgb
        rgba[..., 3] *= op
        x, y = ctx.px(self._kf("x", t, self.x)), ctx.px(self._kf("y", t, self.y))
        p = Patch(rgba, x - size // 2, y - size // 2)
        return canvas.transform_patch(p, 1.0, self._kf("rotation", t, 0.0))


# ---------------- frame effects ----------------

class Vignette(Layer):
    def __init__(self, strength: float = 0.45, radius: float = 0.75, softness: float = 0.5, color="#000000", **kw):
        super().__init__(**kw)
        self.strength, self.radius, self.softness, self.color = strength, radius, softness, color
        self._mask: dict = {}

    def draw(self, frame, ctx, t):
        h, w = frame.shape[:2]
        if (w, h) not in self._mask:
            ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
            d = np.hypot((xs - w / 2) / (w / 2), (ys - h / 2) / (h / 2)) / math.sqrt(2)
            self._mask[(w, h)] = np.clip((d - self.radius + self.softness) / self.softness, 0, 1)[..., None] ** 2
        m = self._mask[(w, h)] * self.strength * self.opacity
        return frame * (1 - m) + np.array(resolve_color(ctx.brand, self.color), np.float32) * m


class ChromaticAberration(Layer):
    """Splits R and B channels horizontally by `amount` design px (optionally pulsing)."""

    def __init__(self, amount: float = 6.0, pulse: float = 0.0, **kw):
        super().__init__(**kw)
        self.amount, self.pulse = amount, pulse

    def draw(self, frame, ctx, t):
        amt = self.amount * (1 + self.pulse * math.sin(t * 2 * math.pi)) * ctx.scale * self.opacity
        d = int(round(amt))
        if d == 0:
            return frame
        out = frame.copy()
        out[:, d:, 0] = frame[:, :-d, 0]
        out[:, :-d, 2] = frame[:, d:, 2]
        return out


class Glow(Layer):
    """Bloom: bright areas above `threshold` are blurred and added back."""

    def __init__(self, threshold: float = 0.75, radius: float = 24.0, intensity: float = 0.6, **kw):
        super().__init__(**kw)
        self.threshold, self.radius, self.intensity = threshold, radius, intensity

    def draw(self, frame, ctx, t):
        lum = frame.max(axis=2, keepdims=True)
        bright = frame * np.clip((lum - self.threshold) / max(1 - self.threshold, 1e-3), 0, 1)
        r = max(self.radius * ctx.scale, 1)
        k = int(r * 3) | 1
        bloom = cv2.GaussianBlur(bright, (k, k), r)
        return np.clip(frame + bloom * self.intensity * self.opacity, 0, 1)


class LightShake(Layer):
    """Subtle continuous jitter (a few design px) — for energy without a full CameraShake."""

    def __init__(self, amount: float = 4.0, frequency: float = 9.0, seed: int = 21, **kw):
        super().__init__(**kw)
        self.amount, self.frequency, self.seed = amount, frequency, seed

    def draw(self, frame, ctx, t):
        dx = self.amount * ctx.scale * smooth_noise(t, self.seed, 2, self.frequency)
        dy = self.amount * ctx.scale * smooth_noise(t, self.seed + 1, 2, self.frequency)
        m = np.float32([[1, 0, dx], [0, 1, dy]])
        return cv2.warpAffine(frame, m, (frame.shape[1], frame.shape[0]), borderMode=cv2.BORDER_REFLECT)


class MotionBlurLayer(Layer):
    """Wraps another layer and averages `samples` sub-frame renders across the shutter angle."""

    def __init__(self, layer: Layer, samples: int = 5, shutter: float = 0.5, fps: float = 30.0, **kw):
        kw.setdefault("start", layer.start)
        kw.setdefault("duration", layer.duration)
        super().__init__(**kw)
        self.layer, self.samples, self.shutter, self.fps = layer, samples, shutter, fps

    def draw(self, frame, ctx, t):
        span = self.shutter / self.fps
        acc = np.zeros_like(frame)
        for i in range(self.samples):
            dt = (i / max(self.samples - 1, 1) - 0.5) * span
            acc += self.layer.draw(frame.copy(), ctx, max(t + dt, 0.0))
        return acc / self.samples


def speed_ramp(t: float, keyframes: list[tuple[float, float]]) -> float:
    """Map output time -> source time for piecewise-linear speed keyframes [(out_t, speed), ...].
    Speed is interpolated linearly between keys and integrated exactly (trapezoids)."""
    ks = sorted(keyframes)
    if t <= ks[0][0]:
        return t * ks[0][1]
    src = ks[0][0] * ks[0][1]
    for (t0, s0), (t1, s1) in zip(ks, ks[1:]):
        if t <= t0:
            break
        seg_end = min(t, t1)
        s_end = s0 + (s1 - s0) * (seg_end - t0) / (t1 - t0)
        src += (s0 + s_end) / 2 * (seg_end - t0)
        if t <= t1:
            return src
    return src + (t - ks[-1][0]) * ks[-1][1]


class SpeedRampLayer(Layer):
    """Time-remaps another layer (e.g. a VideoClipLayer) with speed keyframes."""

    def __init__(self, layer: Layer, keyframes: list[tuple[float, float]], **kw):
        kw.setdefault("start", layer.start)
        super().__init__(**kw)
        self.layer, self.keyframes = layer, keyframes

    def draw(self, frame, ctx, t):
        return self.layer.draw(frame, ctx, speed_ramp(t, self.keyframes))


class GuideRectLayer(Layer):
    """Thin outline rectangle that draws itself on (perimeter progress) — blueprint guide lines.
    rect = (x, y, w, h) design px; angle rotates it about its centre."""

    def __init__(self, rect=(100, 100, 400, 300), color="#FFFFFF", thickness: float = 2.0, draw_duration: float = 0.8,
                 ease: str = "in_out_cubic", angle: float = 0.0, line_opacity: float = 0.8, **kw):
        super().__init__(**kw)
        self.rect, self.color, self.thickness, self.draw_duration = rect, color, thickness, draw_duration
        self.ease, self.angle, self.line_opacity = ease, angle, line_opacity

    def draw(self, frame, ctx, t):
        p = easing.progress(t, 0, self.draw_duration, self.ease)
        if p <= 0:
            return frame
        x, y, w, h = (v * ctx.scale for v in self.rect)
        cx, cy = x + w / 2, y + h / 2
        a = math.radians(self.angle)
        corners = [(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)]
        corners = [((px - cx) * math.cos(a) - (py - cy) * math.sin(a) + cx,
                    (px - cx) * math.sin(a) + (py - cy) * math.cos(a) + cy) for px, py in corners]
        total = 2 * (w + h) * p
        pts = [corners[0]]
        for (x0, y0), (x1, y1) in zip(corners, corners[1:]):
            seg = math.hypot(x1 - x0, y1 - y0)
            if total <= 0:
                break
            f = min(1.0, total / max(seg, 1e-6))
            pts.append((x0 + (x1 - x0) * f, y0 + (y1 - y0) * f))
            total -= seg
        H, W = frame.shape[:2]
        m = np.zeros((H, W), np.uint8)
        th = max(int(round(self.thickness * ctx.scale)), 1)
        cv2.polylines(m, [np.round(np.array(pts) * 4).astype(np.int32)], False, 255, th, lineType=cv2.LINE_AA, shift=2)
        a_m = (m.astype(np.float32) / 255 * self.line_opacity * self.opacity)[..., None]
        return frame * (1 - a_m) + np.array(resolve_color(ctx.brand, self.color), np.float32) * a_m


class PanelWipeLayer(Layer):
    """Solid colour panel (x, y, w, h design px; default full frame) revealed by a hard wipe."""

    def __init__(self, color="primary", rect=None, direction: str = "left", wipe_duration: float = 0.5,
                 ease: str = "in_out_expo", **kw):
        super().__init__(**kw)
        self.color, self.rect, self.direction, self.wipe_duration, self.ease = color, rect, direction, wipe_duration, ease

    def draw(self, frame, ctx, t):
        p = easing.progress(t, 0, self.wipe_duration, self.ease)
        if p <= 0:
            return frame
        H, W = frame.shape[:2]
        x, y, w, h = (0, 0, W, H) if self.rect is None else tuple(int(round(v * ctx.scale)) for v in self.rect)
        if self.direction == "left":
            w = int(round(w * p))
        elif self.direction == "right":
            x, w = x + w - int(round(w * p)), int(round(w * p))
        elif self.direction == "down":
            h = int(round(h * p))
        else:
            y, h = y + h - int(round(h * p)), int(round(h * p))
        x0, y0, x1, y1 = max(x, 0), max(y, 0), min(x + w, W), min(y + h, H)
        if x1 > x0 and y1 > y0:
            frame[y0:y1, x0:x1] = frame[y0:y1, x0:x1] * (1 - self.opacity) + \
                np.array(resolve_color(ctx.brand, self.color), np.float32) * self.opacity
        return frame


class EllipseRingLayer(Layer):
    """Outline ellipse (design px centre + radii) that draws on as an arc."""

    def __init__(self, center=(540, 960), radii=(200, 120), color="#FFFFFF", thickness: float = 30,
                 draw_duration: float = 0.6, ease: str = "out_cubic", start_angle: float = -90, **kw):
        super().__init__(**kw)
        self.center, self.radii, self.color, self.thickness = center, radii, color, thickness
        self.draw_duration, self.ease, self.start_angle = draw_duration, ease, start_angle

    def draw(self, frame, ctx, t):
        p = easing.progress(t, 0, self.draw_duration, self.ease)
        if p <= 0:
            return frame
        H, W = frame.shape[:2]
        m = np.zeros((H, W), np.uint8)
        c = (int(self.center[0] * ctx.scale * 4), int(self.center[1] * ctx.scale * 4))
        ax = (int(self.radii[0] * ctx.scale * 4), int(self.radii[1] * ctx.scale * 4))
        cv2.ellipse(m, c, ax, 0, self.start_angle, self.start_angle + 360 * p, 255,
                    max(int(self.thickness * ctx.scale), 1), lineType=cv2.LINE_AA, shift=2)
        a_m = (m.astype(np.float32) / 255 * self.opacity)[..., None]
        return frame * (1 - a_m) + np.array(resolve_color(ctx.brand, self.color), np.float32) * a_m
