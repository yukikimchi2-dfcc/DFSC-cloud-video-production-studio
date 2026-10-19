"""Image buffers and compositing.

Conventions used across the whole engine:
  * A *frame* is float32 RGB, shape (H, W, 3), values in [0, 1].
  * A *Patch* is float32 straight-alpha RGBA (h, w, 4) placed at integer (x, y) on the frame.
    Patches may extend past the frame edges; compositing clips them.
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class Patch:
    rgba: np.ndarray
    x: int = 0
    y: int = 0

    @property
    def w(self) -> int:
        return self.rgba.shape[1]

    @property
    def h(self) -> int:
        return self.rgba.shape[0]


def hex_to_rgb(color: str | tuple) -> tuple[float, float, float]:
    """'#47B649' / '47B649' / (71,182,73) / (0.28,0.71,0.29) -> floats in [0,1]."""
    if isinstance(color, str):
        s = color.lstrip("#")
        if len(s) == 3:
            s = "".join(c * 2 for c in s)
        return tuple(int(s[i:i + 2], 16) / 255.0 for i in (0, 2, 4))  # type: ignore[return-value]
    vals = tuple(float(c) for c in color[:3])
    return tuple(v / 255.0 for v in vals) if max(vals) > 1.0 else vals  # type: ignore[return-value]


def solid(w: int, h: int, color="#000000") -> np.ndarray:
    frame = np.empty((h, w, 3), np.float32)
    frame[:] = hex_to_rgb(color)
    return frame


def to_uint8(frame: np.ndarray) -> np.ndarray:
    return (np.clip(frame, 0, 1) * 255 + 0.5).astype(np.uint8)


def from_uint8(img: np.ndarray) -> np.ndarray:
    return img.astype(np.float32) / 255.0


def composite(frame: np.ndarray, patch: Patch | None, opacity: float = 1.0, blend: str = "normal") -> np.ndarray:
    """Alpha-composite `patch` over `frame` in place (clipped to frame bounds). Returns frame."""
    if patch is None or opacity <= 0:
        return frame
    H, W = frame.shape[:2]
    x0, y0 = max(patch.x, 0), max(patch.y, 0)
    x1, y1 = min(patch.x + patch.w, W), min(patch.y + patch.h, H)
    if x0 >= x1 or y0 >= y1:
        return frame
    src = patch.rgba[y0 - patch.y:y1 - patch.y, x0 - patch.x:x1 - patch.x]
    a = src[..., 3:4] * opacity
    dst = frame[y0:y1, x0:x1]
    rgb = src[..., :3]
    if blend == "add":
        dst += rgb * a
        np.clip(dst, 0, 1, out=dst)
    elif blend == "screen":
        dst[:] = dst + (1 - (1 - dst) * (1 - rgb) - dst) * a
    elif blend == "multiply":
        dst[:] = dst * (1 - a) + dst * rgb * a
    else:
        dst[:] = dst * (1 - a) + rgb * a
    return frame


def transform_patch(patch: Patch, scale: float = 1.0, rotation_deg: float = 0.0,
                    anchor: tuple[float, float] | None = None) -> Patch:
    """Scale/rotate a patch about `anchor` (absolute frame coords; default = patch centre)."""
    if abs(scale - 1.0) < 1e-4 and abs(rotation_deg) < 1e-4:
        return patch
    if scale <= 1e-3:
        return Patch(np.zeros((1, 1, 4), np.float32), patch.x, patch.y)
    h, w = patch.rgba.shape[:2]
    ax, ay = anchor if anchor else (patch.x + w / 2, patch.y + h / 2)
    lx, ly = ax - patch.x, ay - patch.y
    m = cv2.getRotationMatrix2D((lx, ly), rotation_deg, scale)
    corners = np.array([[0, 0, 1], [w, 0, 1], [0, h, 1], [w, h, 1]], np.float32) @ m.T
    minx, miny = np.floor(corners.min(0)).astype(int)
    maxx, maxy = np.ceil(corners.max(0)).astype(int)
    m[0, 2] -= minx
    m[1, 2] -= miny
    out_w, out_h = max(int(maxx - minx), 1), max(int(maxy - miny), 1)
    premul = patch.rgba.copy()
    premul[..., :3] *= premul[..., 3:4]
    warped = cv2.warpAffine(premul, m, (out_w, out_h), flags=cv2.INTER_LINEAR,
                            borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))
    a = warped[..., 3:4]
    warped[..., :3] = np.where(a > 1e-6, warped[..., :3] / np.maximum(a, 1e-6), 0)
    return Patch(warped, patch.x + minx, patch.y + miny)


def blur_rgba(rgba: np.ndarray, radius: float) -> np.ndarray:
    if radius <= 0:
        return rgba
    k = int(radius * 3) | 1
    premul = rgba.copy()
    premul[..., :3] *= premul[..., 3:4]
    out = cv2.GaussianBlur(premul, (k, k), radius)
    a = out[..., 3:4]
    out[..., :3] = np.where(a > 1e-6, out[..., :3] / np.maximum(a, 1e-6), 0)
    return out


def pad_patch(patch: Patch, pad: int) -> Patch:
    rgba = np.pad(patch.rgba, ((pad, pad), (pad, pad), (0, 0)))
    return Patch(rgba, patch.x - pad, patch.y - pad)


def drop_shadow(patch: Patch, color="#000000", opacity: float = 0.5, blur: float = 8,
                offset: tuple[int, int] = (0, 6)) -> Patch:
    """Return a new patch: shadow underneath the original content."""
    pad = int(blur * 3) + max(abs(offset[0]), abs(offset[1]))
    p = pad_patch(patch, pad)
    shadow = np.zeros_like(p.rgba)
    shadow[..., :3] = hex_to_rgb(color)
    shadow[..., 3] = np.roll(np.roll(p.rgba[..., 3], offset[1], 0), offset[0], 1) * opacity
    shadow = blur_rgba(shadow, blur)
    # composite original over shadow in patch space, keeping alpha
    a_s, a_o = shadow[..., 3:4], p.rgba[..., 3:4]
    a = a_o + a_s * (1 - a_o)
    rgb = (p.rgba[..., :3] * a_o + shadow[..., :3] * a_s * (1 - a_o)) / np.maximum(a, 1e-6)
    return Patch(np.concatenate([rgb, a], axis=-1).astype(np.float32), p.x, p.y)


def resize_cover(img: np.ndarray, w: int, h: int, center: tuple[float, float] = (0.5, 0.5)) -> np.ndarray:
    """Scale to fill (w, h) and crop around `center` (fractions of the source)."""
    sh, sw = img.shape[:2]
    s = max(w / sw, h / sh)
    nw, nh = max(int(round(sw * s)), w), max(int(round(sh * s)), h)
    resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR)
    cx, cy = center[0] * nw, center[1] * nh
    x0 = int(np.clip(cx - w / 2, 0, nw - w))
    y0 = int(np.clip(cy - h / 2, 0, nh - h))
    return resized[y0:y0 + h, x0:x0 + w]
