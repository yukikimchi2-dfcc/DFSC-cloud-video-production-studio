"""Shared helpers for the motion engine: fonts, colours, patch compositing, enter/exit states."""
from __future__ import annotations

import functools
import math
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import ImageFont

from studio.core import easing
from studio.core.canvas import Patch, hex_to_rgb

# Fallback chain when a brand font file is missing (e.g. CJK Black/Thin need fonts-noto-cjk-extra).
_FALLBACK_SPECS = [
    {"path": "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", "index": 3},
    {"path": "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", "index": 3},
]
_NOTO_CJK_TC_INDEX = 3  # inside NotoSansCJK-*.ttc: 0 JP, 1 KR, 2 SC, 3 TC, 4 HK


@functools.lru_cache(maxsize=256)
def _truetype(path: str, index: int, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size=size, index=index)


def get_font(brand, role: str, size: int) -> ImageFont.FreeTypeFont:
    """Resolve a brand font role, guaranteeing a Traditional-Chinese-capable face.

    Noto CJK collections are remapped to the TC face (index 3) when a spec points at the SC
    face (index 2), and missing files fall back to installed Noto Sans CJK TC weights.
    """
    size = max(int(size), 1)
    specs = []
    if brand is not None:
        try:
            specs.append(dict(brand.font_spec(role)))
        except Exception:  # unknown role / malformed spec -> fall back
            pass
    specs += _FALLBACK_SPECS
    for spec in specs:
        path, index = spec["path"], int(spec.get("index", 0))
        if "NotoSansCJK" in Path(path).name and Path(path).suffix == ".ttc" and index == 2:
            index = _NOTO_CJK_TC_INDEX
        if Path(path).exists():
            return _truetype(path, index, size)
    return ImageFont.load_default(size)


def resolve_color(brand, color) -> tuple[float, float, float]:
    """Brand palette key ('primary'), hex string or tuple -> float RGB."""
    if isinstance(color, str) and not color.startswith("#") and brand is not None:
        try:
            color = brand.color(color)
        except KeyError:
            pass
    if isinstance(color, str) and not color.startswith("#"):
        color = {"white": "#FFFFFF", "black": "#000000"}.get(color, "#FFFFFF")
    return hex_to_rgb(color)


def over(dst: Patch, src: Patch | None, opacity: float = 1.0) -> Patch:
    """Composite RGBA `src` over RGBA `dst` in place (both straight alpha, frame coords)."""
    if src is None or opacity <= 0:
        return dst
    x0, y0 = max(dst.x, src.x), max(dst.y, src.y)
    x1, y1 = min(dst.x + dst.w, src.x + src.w), min(dst.y + dst.h, src.y + src.h)
    if x0 >= x1 or y0 >= y1:
        return dst
    s = src.rgba[y0 - src.y:y1 - src.y, x0 - src.x:x1 - src.x]
    d = dst.rgba[y0 - dst.y:y1 - dst.y, x0 - dst.x:x1 - dst.x]
    sa = s[..., 3:4] * opacity
    da = d[..., 3:4]
    oa = sa + da * (1 - sa)
    rgb = (s[..., :3] * sa + d[..., :3] * da * (1 - sa)) / np.maximum(oa, 1e-6)
    d[..., :3] = rgb
    d[..., 3:4] = oa
    return dst


def offset(patch: Patch, dx: float, dy: float) -> Patch:
    return Patch(patch.rgba, patch.x + int(round(dx)), patch.y + int(round(dy)))


def with_opacity(patch: Patch, opacity: float) -> Patch:
    if opacity >= 0.999:
        return patch
    rgba = patch.rgba.copy()
    rgba[..., 3] *= max(opacity, 0.0)
    return Patch(rgba, patch.x, patch.y)


def rounded_rect_mask(w: int, h: int, radius: float, ss: int = 4) -> np.ndarray:
    """Anti-aliased rounded rectangle coverage mask (h, w) float32."""
    w, h = max(int(w), 1), max(int(h), 1)
    r = int(max(0, min(radius, w / 2, h / 2)) * ss)
    big = np.zeros((h * ss, w * ss), np.uint8)
    W, H = w * ss, h * ss
    if r <= 0:
        big[:] = 255
    else:
        cv2.rectangle(big, (r, 0), (W - 1 - r, H - 1), 255, -1)
        cv2.rectangle(big, (0, r), (W - 1, H - 1 - r), 255, -1)
        for cx, cy in ((r, r), (W - 1 - r, r), (r, H - 1 - r), (W - 1 - r, H - 1 - r)):
            cv2.circle(big, (cx, cy), r, 255, -1, lineType=cv2.LINE_AA)
    return cv2.resize(big, (w, h), interpolation=cv2.INTER_AREA).astype(np.float32) / 255


def linear_gradient(w: int, h: int, c0, c1, angle_deg: float = 90.0) -> np.ndarray:
    """(h, w, 3) gradient from c0 to c1. angle 90 = top->bottom, 0 = left->right."""
    a = math.radians(angle_deg)
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    proj = (xs - w / 2) * math.cos(a) + (ys - h / 2) * math.sin(a)
    span = abs(w * math.cos(a)) + abs(h * math.sin(a))
    p = np.clip(proj / max(span, 1e-6) + 0.5, 0, 1)[..., None]
    return (np.array(c0, np.float32) * (1 - p) + np.array(c1, np.float32) * p).astype(np.float32)


def solid_patch(w: int, h: int, color, alpha: np.ndarray | None = None) -> Patch:
    rgba = np.zeros((max(int(h), 1), max(int(w), 1), 4), np.float32)
    rgba[..., :3] = color
    rgba[..., 3] = 1.0 if alpha is None else alpha
    return Patch(rgba)


def smooth_noise(t: float, seed: int, octaves: int = 3, freq: float = 1.0) -> float:
    """Deterministic smooth 1-D noise in roughly [-1, 1] (sum of seeded sines)."""
    rng = np.random.default_rng(seed)
    phases = rng.uniform(0, 2 * math.pi, octaves)
    freqs = freq * (1.7 ** np.arange(octaves)) * rng.uniform(0.8, 1.2, octaves)
    amps = 0.5 ** np.arange(octaves)
    return float(np.sum(amps * np.sin(2 * math.pi * freqs * t + phases)) / amps.sum())


@dataclass
class AnimState:
    opacity: float = 1.0
    dx: float = 0.0       # design px
    dy: float = 0.0
    scale: float = 1.0
    rotation: float = 0.0
    reveal: float = 1.0   # 0..1 for wipe / expand style entrances


_DIST = 140.0  # design px travel for slide/fly moves


def _apply(style: str, p: float, s: AnimState, entering: bool) -> None:
    """Mutate state for style at eased progress p (1 = fully on screen)."""
    q = 1 - p
    if style in ("none", None):
        return
    if style == "fade":
        s.opacity *= p
    elif style in ("slide_up", "rise"):
        s.dy += _DIST * q
        s.opacity *= p
    elif style == "slide_down":
        s.dy -= _DIST * q
        s.opacity *= p
    elif style == "slide_left":
        s.dx += _DIST * 2 * q
        s.opacity *= p
    elif style == "slide_right":
        s.dx -= _DIST * 2 * q
        s.opacity *= p
    elif style == "fly_left":   # travels far from off-screen right
        s.dx += 1200 * q
    elif style == "fly_right":
        s.dx -= 1200 * q
    elif style == "fly_up":
        s.dy += 1400 * q
    elif style == "scale":
        s.scale *= max(p, 0.0)
        s.opacity *= min(1.0, p * 3)
    elif style == "pop":
        s.scale *= max(p, 0.0)
    elif style == "slam":   # comes from big + transparent down to size
        s.scale *= 1 + 1.5 * q
        s.opacity *= min(1.0, p * 2)
    elif style == "spin":
        s.rotation += 180 * q
        s.scale *= max(p, 0.0)
    elif style in ("expand", "wipe"):
        s.reveal *= max(p, 0.0)
    elif style == "drop":
        s.dy += (-_DIST if entering else _DIST * 3) * q
        s.opacity *= p
    else:
        raise ValueError(f"Unknown enter/exit style '{style}'")


_DEFAULT_EASE = {"pop": "out_back", "slam": "out_expo", "spin": "out_back", "drop": "out_bounce"}


def enter_exit_state(t: float, enter: str = "fade", enter_duration: float = 0.5,
                     exit: str | None = None, exit_start: float | None = None, exit_duration: float = 0.4,
                     ease: str | None = None) -> AnimState:
    """Combined state for a layer at local time t with an entrance and an optional exit."""
    s = AnimState()
    if enter and enter != "none":
        p = easing.progress(t, 0, enter_duration, ease or _DEFAULT_EASE.get(enter, "out_cubic"))
        _apply(enter, p, s, True)
    if exit and exit != "none" and exit_start is not None and t >= exit_start:
        p = 1 - easing.progress(t, exit_start, exit_duration, "in_cubic")
        _apply(exit, p, s, False)
    return s


def in_expo(t: float) -> float:
    """Exponential ease-in (not in studio.core.easing)."""
    return 0.0 if t <= 0 else 2 ** (10 * t - 10)


def _luminance(rgb) -> float:
    def ch(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast_ratio(a, b) -> float:
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def readable_on(brand, background, preferred="text", min_ratio: float = 2.5) -> str:
    """Pick `preferred` if it is readable on `background`, else near-black or white (whichever contrasts more).
    Templates use colour 'auto' to request this."""
    bg = resolve_color(brand, background)
    pref = resolve_color(brand, preferred)
    if contrast_ratio(pref, bg) >= min_ratio:
        return "#%02X%02X%02X" % tuple(round(c * 255) for c in pref)
    dark, light = (0.07, 0.07, 0.07), (1.0, 1.0, 1.0)
    return "#121212" if contrast_ratio(dark, bg) >= contrast_ratio(light, bg) else "#FFFFFF"
