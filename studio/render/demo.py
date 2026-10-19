"""Synthetic TEST timelines used by the render queue, smoke tests and setup verification.

Everything here is generated — no real footage — and visibly watermarked as test material.
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw

from ..brand import load_brand
from ..core import canvas, easing, vector
from ..core.canvas import Patch
from ..core.io import run_ffmpeg
from ..core.timeline import FuncLayer, Layer, Timeline

WATERMARK = "TEST · 合成測試素材"


class _TextLayer(Layer):
    """Minimal static text (the full typography engine lives in studio.motion.typography)."""

    def __init__(self, text: str, y: float, size: float, color="#FFFFFF", role="body", **kw):
        super().__init__(**kw)
        self.text, self.y, self.size, self.color, self.role = text, y, size, color, role
        self._cache: dict = {}

    def render(self, ctx, t):
        size = ctx.px(self.size)
        if size not in self._cache:
            font = ctx.brand.font(self.role, size)
            x0, y0, x1, y1 = font.getbbox(self.text)
            img = Image.new("RGBA", (x1 - x0 + 4, y1 - y0 + 4), (0, 0, 0, 0))
            ImageDraw.Draw(img).text((2 - x0, 2 - y0), self.text, font=font,
                                     fill=tuple(int(c * 255) for c in canvas.hex_to_rgb(ctx.brand.color(self.color))))
            self._cache[size] = np.asarray(img, np.float32) / 255
        rgba = self._cache[size]
        return Patch(rgba, (ctx.width - rgba.shape[1]) // 2, ctx.px(self.y))


class _StarLayer(Layer):
    def __init__(self, logo: str | None, size: float, y: float, **kw):
        super().__init__(**kw)
        self.logo, self.size, self.y = logo, size, y

    def render(self, ctx, t):
        shape = ctx.brand.logo_shape(self.logo) if self.logo and self.logo in ctx.brand.logos else vector.star_shape()
        p = vector.render_shape(shape, ctx.px(self.size))
        p.x, p.y = (ctx.width - p.w) // 2, ctx.px(self.y)
        k = easing.progress(t, 0, 1.2, "out_expo")
        return canvas.transform_patch(p, scale=0.2 + 0.8 * k, rotation_deg=(1 - k) * 135)


def _moving_gradient(frame, ctx, t):
    h, w = frame.shape[:2]
    y = np.linspace(0, 1, h, dtype=np.float32)[:, None]
    x = np.linspace(0, 1, w, dtype=np.float32)[None, :]
    wave = 0.5 + 0.5 * np.sin(2 * math.pi * (x * 0.8 + y * 0.6 - t * 0.25))
    frame *= (0.85 + 0.15 * wave)[..., None]
    return frame


def build_test_card(project_id: str | None = "dfsc-2027", duration: float = 4.0, fps: float = 30,
                    text: str = "Cloud Video Studio", audio: str | None = None) -> Timeline:
    brand = load_brand(project_id)
    bg = brand.colors.get("background", "#000000")
    tl = Timeline(fps=fps, duration=duration, background=bg, brand=brand, audio=audio)
    logo = "north_star_tricolor" if "north_star_tricolor" in brand.logos else None
    tl.add(
        FuncLayer(_moving_gradient, z=0),
        _StarLayer(logo, size=700, y=380, z=1),
        _TextLayer(text, y=1200, size=72, role="title", color=brand.colors.get("text", "#FFFFFF"), z=2),
        _TextLayer(WATERMARK, y=1700, size=40, color="#FFFFFF", z=10, opacity=0.8),
        FuncLayer(lambda f, c, t: _frame_counter(f, c, t), z=11),
    )
    return tl


def _frame_counter(frame, ctx, t):
    # a moving bar makes frozen-frame detection meaningful in QC tests
    x = int((t * 0.5 % 1.0) * (ctx.width - ctx.px(60)))
    frame[ctx.height - ctx.px(20):, x:x + ctx.px(60)] = 1.0
    return frame


def make_test_tone(path, duration: float = 4.0, freq: int = 440, sample_rate: int = 48000) -> str:
    """Synthetic audio bed: a sine tone at roughly -20 dBFS."""
    run_ffmpeg(["-f", "lavfi", "-i", f"sine=frequency={freq}:sample_rate={sample_rate}:duration={duration}",
                "-af", "volume=0.1", "-ac", "2", str(path)])
    return str(path)
