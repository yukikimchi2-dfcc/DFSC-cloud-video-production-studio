"""Stickers: PNG images or emoji with white outline, drop shadow and playful motion.

Emoji come from Noto Color Emoji (OFL licensed, installed with fonts-noto-color-emoji). It is a
bitmap font that only renders at size 109, so glyphs are rasterised once and scaled.
Apple Color Emoji is never assumed to exist on cloud Linux.
"""
from __future__ import annotations

import functools
import math
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from studio.core import canvas, easing
from studio.core.canvas import Patch
from studio.core.timeline import Layer

from ._util import enter_exit_state, offset, resolve_color, with_opacity

EMOJI_FONT = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"


@functools.lru_cache(maxsize=128)
def emoji_image(char: str) -> np.ndarray:
    """RGBA float32 image of an emoji (~136 px), cropped to content."""
    if not Path(EMOJI_FONT).exists():
        raise FileNotFoundError(f"Emoji font missing: {EMOJI_FONT} (install fonts-noto-color-emoji)")
    font = ImageFont.truetype(EMOJI_FONT, 109)
    im = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((20, 20), char, font=font, embedded_color=True)
    bbox = im.getbbox()
    if bbox is None:
        raise ValueError(f"Emoji font has no glyph for {char!r}")
    return np.asarray(im.crop(bbox), np.float32) / 255


@functools.lru_cache(maxsize=64)
def _load_png(path: str) -> np.ndarray:
    img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise FileNotFoundError(path)
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGRA)
    elif img.shape[2] == 3:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
    return cv2.cvtColor(img, cv2.COLOR_BGRA2RGBA).astype(np.float32) / 255


def add_outline(rgba: np.ndarray, width: int, color=(1.0, 1.0, 1.0)) -> np.ndarray:
    """Die-cut sticker outline: dilate alpha and put a solid colour underneath."""
    if width <= 0:
        return rgba
    pad = width + 2
    src = np.pad(rgba, ((pad, pad), (pad, pad), (0, 0)))
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * width + 1, 2 * width + 1))
    ring = cv2.dilate(src[..., 3], k)
    ring = cv2.GaussianBlur(ring, (3, 3), 0.8)
    a_o, a_r = src[..., 3:4], ring[..., None]
    a = a_o + a_r * (1 - a_o)
    rgb = (src[..., :3] * a_o + np.array(color, np.float32) * a_r * (1 - a_o)) / np.maximum(a, 1e-6)
    return np.concatenate([rgb, a], -1).astype(np.float32)


class StickerLayer(Layer):
    """source: path to a PNG, or an emoji string like '🚀'. x, y = centre in design px.

    enter: pop | fly_left | fly_right | fly_up | fade | spin | drop; exit: same set or None.
    wobble: rotation amplitude in degrees once settled; float_amp: design px vertical bob.
    """

    def __init__(self, source: str, x: float = 540, y: float = 960, height: float = 220, outline: float = 10,
                 outline_color="#FFFFFF", shadow: bool = True, rotation: float = 0.0, enter: str = "pop",
                 enter_duration: float = 0.45, exit: str | None = None, exit_start: float | None = None,
                 exit_duration: float = 0.35, wobble: float = 6.0, wobble_speed: float = 1.4,
                 float_amp: float = 0.0, **kw):
        super().__init__(**kw)
        self.source, self.x, self.y, self.height = source, x, y, height
        self.outline, self.outline_color, self.shadow, self.rotation = outline, outline_color, shadow, rotation
        self.enter, self.enter_duration = enter, enter_duration
        self.exit, self.exit_duration = exit, exit_duration
        self.exit_start = exit_start if exit_start is not None else (
            self.duration - exit_duration if exit and self.duration is not None else None)
        self.wobble, self.wobble_speed, self.float_amp = wobble, wobble_speed, float_amp
        self._cache: dict = {}

    def _base(self, ctx) -> Patch:
        key = (ctx.px(self.height), id(ctx.brand))
        if key not in self._cache:
            is_file = Path(self.source).suffix.lower() in (".png", ".webp") and Path(self.source).exists()
            img = _load_png(str(self.source)) if is_file else emoji_image(self.source)
            target_h = max(ctx.px(self.height), 2)
            s = target_h / img.shape[0]
            img = cv2.resize(img, (max(int(img.shape[1] * s), 1), target_h), interpolation=cv2.INTER_AREA)
            img = add_outline(img, int(round(self.outline * ctx.scale)), resolve_color(ctx.brand, self.outline_color))
            p = Patch(img)
            if self.shadow:
                p = canvas.drop_shadow(p, "#000000", 0.35, 10 * ctx.scale, (0, int(8 * ctx.scale)))
            self._cache[key] = p
        return self._cache[key]

    def render(self, ctx, t):
        base = self._base(ctx)
        st = enter_exit_state(t, self.enter, self.enter_duration, self.exit, self.exit_start, self.exit_duration,
                              "out_elastic" if self.enter == "pop" else None)
        settle = easing.clamp01((t - self.enter_duration) / 0.3)
        rot = self.rotation + st.rotation + self.wobble * settle * math.sin(2 * math.pi * self.wobble_speed * t)
        bob = self.float_amp * settle * math.sin(2 * math.pi * 0.6 * t)
        p = Patch(base.rgba, ctx.px(self.x) - base.w // 2, ctx.px(self.y) - base.h // 2)
        p = canvas.transform_patch(p, max(st.scale, 0.0), rot)
        p = offset(p, st.dx * ctx.scale, (st.dy + bob) * ctx.scale)
        return with_opacity(p, st.opacity)
