"""Timeline: an ordered stack of time-bounded layers rendered frame by frame.

Layers come in two flavours:
  * content layers implement `render(ctx, t) -> Patch | None` (text, cards, stickers, logos ...)
  * frame layers override `draw(frame, ctx, t) -> frame` to process the whole frame
    (camera moves, transitions, colour grading, vignette ...)
`t` passed to a layer is *local* time: seconds since the layer's own start.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import cv2
import numpy as np

from . import canvas
from .canvas import Patch
from .io import VideoWriter, probe, read_frames


@dataclass
class RenderContext:
    width: int
    height: int
    fps: float
    t: float = 0.0               # global time
    frame_index: int = 0
    brand: Any = None            # studio.brand.BrandKit
    safe_area: dict = field(default_factory=lambda: {"top": 0.1, "bottom": 0.18, "left": 0.06, "right": 0.12})
    scale: float = 1.0           # output_height / design_height — lets 1080p designs render at 720p preview

    def safe_rect(self) -> tuple[int, int, int, int]:
        sa = self.safe_area
        return (int(self.width * sa["left"]), int(self.height * sa["top"]),
                int(self.width * (1 - sa["right"])), int(self.height * (1 - sa["bottom"])))

    def px(self, v: float) -> int:
        """Convert a design-space pixel value (1080x1920 reference) to output pixels."""
        return int(round(v * self.scale))


class Layer:
    def __init__(self, start: float = 0.0, duration: float | None = None, z: int = 0,
                 opacity: float = 1.0, blend: str = "normal", name: str | None = None):
        self.start, self.duration, self.z = start, duration, z
        self.opacity, self.blend = opacity, blend
        self.name = name or type(self).__name__

    @property
    def end(self) -> float:
        return float("inf") if self.duration is None else self.start + self.duration

    def active(self, t: float) -> bool:
        return self.start <= t < self.end

    def render(self, ctx: RenderContext, t: float) -> Patch | None:  # pragma: no cover - interface
        return None

    def draw(self, frame: np.ndarray, ctx: RenderContext, t: float) -> np.ndarray:
        return canvas.composite(frame, self.render(ctx, t), self.opacity, self.blend)


class SolidLayer(Layer):
    def __init__(self, color="#000000", **kw):
        super().__init__(**kw)
        self.color = canvas.hex_to_rgb(color)

    def draw(self, frame, ctx, t):
        frame[:] = frame * (1 - self.opacity) + np.array(self.color, np.float32) * self.opacity
        return frame


class FuncLayer(Layer):
    """Ad-hoc layer from a function `fn(frame, ctx, t) -> frame`. Handy for tests and one-offs."""

    def __init__(self, fn: Callable[[np.ndarray, RenderContext, float], np.ndarray], **kw):
        super().__init__(**kw)
        self.fn = fn

    def draw(self, frame, ctx, t):
        return self.fn(frame, ctx, t)


class FrameSource:
    """Sequential-friendly frame access to a video file with a one-frame cache."""

    def __init__(self, path: str | Path, width: int, height: int, fit: str = "cover",
                 focus: tuple[float, float] = (0.5, 0.5)):
        self.path, self.width, self.height, self.fit, self.focus = str(path), width, height, fit, focus
        self.info = probe(path)
        self._iter = None
        self._next_t = None
        self._last: tuple[float, np.ndarray] | None = None

    def _convert(self, img: np.ndarray) -> np.ndarray:
        if self.fit == "contain":
            s = min(self.width / img.shape[1], self.height / img.shape[0])
            r = cv2.resize(img, (int(img.shape[1] * s), int(img.shape[0] * s)), interpolation=cv2.INTER_AREA)
            out = np.zeros((self.height, self.width, 3), np.uint8)
            y, x = (self.height - r.shape[0]) // 2, (self.width - r.shape[1]) // 2
            out[y:y + r.shape[0], x:x + r.shape[1]] = r
            return out
        return canvas.resize_cover(img, self.width, self.height, self.focus)

    def frame_at(self, t: float) -> np.ndarray:
        fps = self.info.fps or 30.0
        t = min(max(t, 0.0), max(self.info.duration - 1.0 / fps, 0.0))
        if self._last and abs(self._last[0] - t) < 0.5 / fps:
            return self._last[1]
        # restart decoding on seeks; otherwise advance sequentially
        if self._iter is None or self._next_t is None or t < self._next_t - 0.5 / fps or t > self._next_t + 1.0:
            self._iter = read_frames(self.path, start=t)
            self._next_t = t
        img = None
        while self._next_t <= t + 0.5 / fps:
            nxt = next(self._iter, None)
            if nxt is None:
                break
            img = nxt
            self._next_t += 1.0 / fps
        if img is None:
            img = self._last[1] if self._last else np.zeros((self.height, self.width, 3), np.uint8)
            frame = img if img.shape[:2] == (self.height, self.width) else self._convert(img)
        else:
            frame = self._convert(img)
        self._last = (t, frame)
        return frame


class VideoClipLayer(Layer):
    """Places a source video (from `src_in`) on the timeline, scaled to fill the frame."""

    def __init__(self, path: str | Path, src_in: float = 0.0, speed: float = 1.0, fit: str = "cover",
                 focus: tuple[float, float] = (0.5, 0.5), **kw):
        super().__init__(**kw)
        self.path, self.src_in, self.speed, self.fit, self.focus = str(path), src_in, speed, fit, focus
        self._source: FrameSource | None = None
        if self.duration is None:
            self.duration = (probe(path).duration - src_in) / speed

    def draw(self, frame, ctx, t):
        if self._source is None or (self._source.width, self._source.height) != (ctx.width, ctx.height):
            self._source = FrameSource(self.path, ctx.width, ctx.height, self.fit, self.focus)
        img = canvas.from_uint8(self._source.frame_at(self.src_in + t * self.speed))
        frame[:] = frame * (1 - self.opacity) + img * self.opacity
        return frame


class ImageLayer(Layer):
    """Still image (RGB/RGBA file or array) positioned in design-space pixels."""

    def __init__(self, image: str | Path | np.ndarray, x: float = 0, y: float = 0,
                 height: float | None = None, **kw):
        super().__init__(**kw)
        if isinstance(image, (str, Path)):
            img = cv2.imread(str(image), cv2.IMREAD_UNCHANGED)
            if img is None:
                raise FileNotFoundError(image)
            img = cv2.cvtColor(img, cv2.COLOR_BGRA2RGBA if img.shape[2] == 4 else cv2.COLOR_BGR2RGB)
            image = img
        if image.dtype == np.uint8:
            image = image.astype(np.float32) / 255
        if image.shape[2] == 3:
            image = np.dstack([image, np.ones(image.shape[:2], np.float32)])
        self.image, self.x, self.y, self.height = image, x, y, height
        self._cache: tuple[float, Patch] | None = None

    def render(self, ctx, t):
        target_h = ctx.px(self.height) if self.height else ctx.px(self.image.shape[0])
        if not self._cache or self._cache[0] != target_h:
            s = target_h / self.image.shape[0]
            img = cv2.resize(self.image, (max(int(self.image.shape[1] * s), 1), target_h), interpolation=cv2.INTER_AREA)
            self._cache = (target_h, Patch(img))
        p = self._cache[1]
        return Patch(p.rgba, ctx.px(self.x), ctx.px(self.y))


class Timeline:
    DESIGN_HEIGHT = 1920  # all layer geometry is authored at 1080x1920 and scaled to the output

    def __init__(self, width: int = 1080, height: int = 1920, fps: float = 30.0, duration: float = 5.0,
                 background="#000000", brand=None, safe_area: dict | None = None, audio: str | Path | None = None):
        self.width, self.height, self.fps, self.duration = width, height, fps, duration
        self.background, self.brand, self.audio = background, brand, audio
        self.safe_area = safe_area
        self.layers: list[Layer] = []

    def add(self, *layers: Layer) -> "Timeline":
        self.layers.extend(layers)
        return self

    @property
    def n_frames(self) -> int:
        return int(round(self.duration * self.fps))

    def context(self, width: int | None = None, height: int | None = None) -> RenderContext:
        w, h = width or self.width, height or self.height
        ctx = RenderContext(w, h, self.fps, brand=self.brand, scale=h / self.DESIGN_HEIGHT)
        if self.safe_area:
            ctx.safe_area = self.safe_area
        return ctx

    def render_frame(self, t: float, ctx: RenderContext | None = None) -> np.ndarray:
        ctx = ctx or self.context()
        ctx.t = t
        ctx.frame_index = int(round(t * self.fps))
        frame = canvas.solid(ctx.width, ctx.height, self.background)
        for layer in sorted(self.layers, key=lambda l: l.z):  # stable: insertion order within same z
            if layer.active(t):
                frame = layer.draw(frame, ctx, t - layer.start)
        return frame

    def render(self, path: str | Path, width: int | None = None, height: int | None = None,
               start: float = 0.0, end: float | None = None, crf: int = 18, preset: str = "medium",
               audio_path: str | Path | None = None, audio_bitrate: str = "192k",
               progress: Callable[[int, int], None] | None = None) -> Path:
        """Encode [start, end) of the timeline to `path`. Width/height let a preview downscale."""
        ctx = self.context(width, height)
        end = self.duration if end is None else min(end, self.duration)
        first, last = int(round(start * self.fps)), int(round(end * self.fps))
        total = last - first
        with VideoWriter(path, ctx.width, ctx.height, self.fps, crf=crf, preset=preset,
                         audio_path=audio_path, audio_bitrate=audio_bitrate) as writer:
            for i in range(first, last):
                writer.write(canvas.to_uint8(self.render_frame(i / self.fps, ctx)))
                if progress:
                    progress(i - first + 1, total)
        return Path(path)
