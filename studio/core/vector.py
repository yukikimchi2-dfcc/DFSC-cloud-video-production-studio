"""Vector shapes: bezier flattening + anti-aliased polygon rasterisation into RGBA patches.

Shapes are stored as JSON (see projects/<id>/brand/logos/*.json) in this form:
    {"viewbox": [w, h], "paths": [{"fill": "#1861AE", "subpaths": [[[x, y], ...], ...]}]}
Subpaths are already flattened polygons, so rendering needs no SVG parser.
"""
from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

from .canvas import Patch, hex_to_rgb

_SS = 4  # supersampling factor for anti-aliasing


def flatten_cubic(p0, p1, p2, p3, steps: int = 16) -> list[tuple[float, float]]:
    t = np.linspace(0, 1, steps + 1)[1:, None]
    pts = ((1 - t) ** 3) * p0 + 3 * ((1 - t) ** 2) * t * p1 + 3 * (1 - t) * t * t * p2 + (t ** 3) * p3
    return [tuple(map(float, p)) for p in pts]


def load_shape(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def render_shape(shape: dict, height: int, colors: dict[str, str] | None = None,
                 opacity: float = 1.0) -> Patch:
    """Rasterise `shape` scaled to `height` px. `colors` remaps fills, e.g. {"#231F20": "#FFFFFF"}."""
    vw, vh = shape["viewbox"]
    s = height / vh
    w = max(int(round(vw * s)), 1)
    remap = {k.upper(): v for k, v in (colors or {}).items()}
    # premultiplied accumulation at output resolution; each path is supersampled only inside its bbox
    out = np.zeros((height, w, 4), np.float32)
    for path in shape["paths"]:
        polys = [np.asarray(sp, np.float64) * s for sp in path["subpaths"] if len(sp) >= 3]
        if not polys:
            continue
        pts = np.concatenate(polys)
        x0, y0 = np.maximum(np.floor(pts.min(0)).astype(int), 0)
        x1, y1 = np.minimum(np.ceil(pts.max(0)).astype(int) + 1, [w, height])
        if x1 <= x0 or y1 <= y0:
            continue
        mask = np.zeros(((y1 - y0) * _SS, (x1 - x0) * _SS), np.uint8)
        # cv2.fillPoly with several contours uses the even-odd rule -> compound-path holes work
        local = [np.round((p - [x0, y0]) * _SS).astype(np.int32) for p in polys]
        cv2.fillPoly(mask, local, 255, lineType=cv2.LINE_8)
        cov = cv2.resize(mask, (x1 - x0, y1 - y0), interpolation=cv2.INTER_AREA).astype(np.float32)[..., None] / 255
        fill = np.array(hex_to_rgb(remap.get(path["fill"].upper(), path["fill"])), np.float32)
        region = out[y0:y1, x0:x1]
        region[..., :3] = fill * cov + region[..., :3] * (1 - cov)
        region[..., 3:4] = cov + region[..., 3:4] * (1 - cov)
    a = out[..., 3:4]
    out[..., :3] = np.where(a > 1e-6, out[..., :3] / np.maximum(a, 1e-6), 0)
    out[..., 3] *= opacity
    return Patch(out)


def star_shape(points: int = 4, outer: float = 1.0, inner: float = 0.28, rotation_deg: float = 45) -> dict:
    """Procedural pointed star (default looks like the DFSC North Star) as a shape dict."""
    angles = np.deg2rad(rotation_deg) + np.arange(points * 2) * np.pi / points
    radii = np.where(np.arange(points * 2) % 2 == 0, outer, inner)
    pts = np.stack([np.cos(angles) * radii, np.sin(angles) * radii], 1) + outer
    return {"viewbox": [outer * 2, outer * 2], "paths": [{"fill": "#FFFFFF", "subpaths": [pts.tolist()]}]}
