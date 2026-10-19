"""Typography engine: Traditional Chinese + English text with per-character animation.

Layout is CJK-aware (every Han character is a break opportunity, Latin words wrap whole,
closing punctuation never starts a line). Text can run horizontally or as vertical stacked
CJK columns (right-to-left), like 第十一屆 / 北極星 on the DFSC key visual.

    TextLayer("啟航 北極星", x=540, y=600, size=140, role="title", animation="slam",
              stagger=0.06, stroke=6, shadow={"blur": 10}, sweep={"start": 1.0})
"""
from __future__ import annotations

import functools
import math
import re
from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from studio.core import canvas, easing
from studio.core.canvas import Patch
from studio.core.timeline import Layer, RenderContext

from ._util import get_font, resolve_color

_NO_LINE_START = set("，。、！？：；」』）》〉】,.!?:;)]}%…")
_CJK = re.compile(r"[⺀-鿿豈-﫿＀-￯　-〿]")


def is_cjk(ch: str) -> bool:
    return bool(_CJK.match(ch))


def tokenize(text: str) -> list[str]:
    """Split into wrap units: single CJK chars, Latin words (with trailing space), spaces."""
    tokens: list[str] = []
    buf = ""
    for ch in text:
        if is_cjk(ch):
            if buf:
                tokens.append(buf)
                buf = ""
            tokens.append(ch)
        elif ch == " ":
            tokens.append(buf + " ")
            buf = ""
        else:
            buf += ch
    if buf:
        tokens.append(buf)
    return tokens


def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: float | None, tracking: float = 0.0) -> list[str]:
    """Greedy wrap honouring explicit newlines and CJK kinsoku (no punctuation at line start)."""
    lines: list[str] = []
    for para in text.split("\n"):
        if max_width is None:
            lines.append(para)
            continue
        cur = ""
        for tok in tokenize(para):
            trial = cur + tok
            if cur and _line_width(trial.rstrip(), font, tracking) > max_width:
                if tok[0] in _NO_LINE_START:  # keep closing punctuation with the previous char
                    cur = trial
                    continue
                lines.append(cur.rstrip())
                cur = tok.lstrip()
            else:
                cur = trial
        lines.append(cur.rstrip())
    return lines


def _line_width(line: str, font, tracking: float) -> float:
    if not line:
        return 0.0
    return sum(font.getlength(c) for c in line) + tracking * (len(line) - 1)


@functools.lru_cache(maxsize=8192)
def _glyph(font: ImageFont.FreeTypeFont, ch: str, stroke: int) -> tuple[np.ndarray, int]:
    """Rasterise one glyph -> (mask (h, w, 2) float32 [fill, stroke], pad). Top of image = ascender - pad."""
    ascent, descent = font.getmetrics()
    pad = stroke + max(2, int(font.size * 0.12))
    adv = max(int(math.ceil(font.getlength(ch))), 1)
    w, h = adv + 2 * pad, ascent + descent + 2 * pad
    fill = Image.new("L", (w, h), 0)
    ImageDraw.Draw(fill).text((pad, pad), ch, font=font, fill=255, anchor="la")
    if stroke > 0:
        st = Image.new("L", (w, h), 0)
        ImageDraw.Draw(st).text((pad, pad), ch, font=font, fill=255, anchor="la",
                                stroke_width=stroke, stroke_fill=255)
        st_arr = np.asarray(st, np.float32) / 255
    else:
        st_arr = np.zeros((h, w), np.float32)
    return np.dstack([np.asarray(fill, np.float32) / 255, st_arr]), pad


@dataclass
class _Char:
    ch: str
    x: float          # top-left of the glyph cell (ascender line), output px, block-local
    y: float
    adv: float
    index: int        # animation order
    line: int


@dataclass
class _Layout:
    chars: list[_Char]
    width: float
    height: float
    line_boxes: list[tuple[float, float, float, float]]  # x, y, w, baseline_y per line/column
    font: ImageFont.FreeTypeFont
    stroke: int
    line_h: float


CHAR_ANIMATIONS = ("none", "appear", "typewriter", "fade", "bounce", "rotate", "fly_in", "slam", "scale", "pop", "drop")
EXIT_ANIMATIONS = ("none", "fade", "fly_out", "scale_out", "drop", "typewriter")


class TextLayer(Layer):
    """Animated text block positioned in design-space pixels (1080x1920 reference).

    x/y: anchor point. align: 'left' | 'center' | 'right' (horizontal anchor + line alignment);
    valign: 'top' | 'middle' | 'bottom'. size is the font size in design px.
    animation (per char, staggered): see CHAR_ANIMATIONS. exit: see EXIT_ANIMATIONS.
    underline = {"color", "thickness", "start", "duration", "offset"}; sweep = {"start", "duration",
    "width", "color", "intensity"}; mask_reveal = {"direction": left|right|up|down, "start", "duration"}.
    gradient = {"from": color, "to": color, "angle": 90}; shadow = {"color", "opacity", "blur", "offset"}.
    """

    def __init__(self, text: str, x: float = 540, y: float = 960, size: float = 80, role: str = "title",
                 color="text", align: str = "center", valign: str = "top", max_width: float | None = None,
                 tracking: float = 0.0, line_spacing: float = 1.15, stroke: float = 0, stroke_color="#000000",
                 shadow: dict | None = None, gradient: dict | None = None, vertical: bool = False,
                 animation: str = "fade", stagger: float = 0.04, char_duration: float = 0.35, ease: str | None = None,
                 exit: str | None = None, exit_start: float | None = None, exit_duration: float = 0.3,
                 exit_stagger: float = 0.0, underline: dict | None = None, sweep: dict | None = None,
                 mask_reveal: dict | None = None, safe_clamp: bool = True, rotation: float = 0.0, **kw):
        super().__init__(**kw)
        if animation not in CHAR_ANIMATIONS:
            raise ValueError(f"animation must be one of {CHAR_ANIMATIONS}")
        if exit not in (None, *EXIT_ANIMATIONS):
            raise ValueError(f"exit must be one of {EXIT_ANIMATIONS}")
        self.text, self.x, self.y, self.size, self.role = text, x, y, size, role
        self.color, self.align, self.valign, self.max_width = color, align, valign, max_width
        self.tracking, self.line_spacing, self.stroke, self.stroke_color = tracking, line_spacing, stroke, stroke_color
        self.shadow, self.gradient, self.vertical = shadow, gradient, vertical
        self.animation, self.stagger, self.char_duration, self.ease = animation, stagger, char_duration, ease
        self.exit, self.exit_start, self.exit_duration, self.exit_stagger = exit, exit_start, exit_duration, exit_stagger
        if self.exit and self.exit_start is None and self.duration is not None:
            self.exit_start = max(self.duration - exit_duration - exit_stagger * max(len(text) - 1, 0), 0)
        self.underline, self.sweep, self.mask_reveal, self.safe_clamp = underline, sweep, mask_reveal, safe_clamp
        self.rotation = rotation  # whole-block rotation (deg, CCW) about the anchor point, e.g. 90 for sideways English
        self._layout_cache: dict = {}

    # ---------- layout ----------
    def layout(self, ctx: RenderContext) -> _Layout:
        key = (ctx.width, ctx.height, ctx.scale, id(ctx.brand))
        if key in self._layout_cache:
            return self._layout_cache[key]
        font = get_font(ctx.brand, self.role, ctx.px(self.size))
        tracking = self.tracking * ctx.scale
        stroke = int(round(self.stroke * ctx.scale))
        ascent, descent = font.getmetrics()
        line_h = (ascent + descent) * self.line_spacing
        chars: list[_Char] = []
        boxes = []
        idx = 0
        if self.vertical:
            cols = self.text.split("\n")
            cell = font.size * 1.0 + tracking   # square CJK cell
            col_w = font.size * self.line_spacing
            n = len(cols)
            for ci, col in enumerate(cols):
                cx = (n - 1 - ci) * col_w  # right-to-left columns
                for ri, ch in enumerate(col):
                    adv = font.getlength(ch)
                    chars.append(_Char(ch, cx + (font.size - adv) / 2, ri * cell, adv, idx, ci))
                    idx += 1
                boxes.append((cx, 0, font.size, len(col) * cell))
            width = (n - 1) * col_w + font.size
            height = max((len(c) for c in cols), default=0) * cell - tracking
        else:
            max_w = None
            if self.max_width is not None:
                max_w = self.max_width * ctx.scale
            elif self.safe_clamp:
                sx0, _, sx1, _ = ctx.safe_rect()
                max_w = sx1 - sx0
            lines = wrap_text(self.text, font, max_w, tracking)
            widths = [_line_width(l, font, tracking) for l in lines]
            width = max(widths, default=0)
            for li, (line, lw) in enumerate(zip(lines, widths)):
                lx = {"left": 0, "center": (width - lw) / 2, "right": width - lw}[self.align]
                y = li * line_h
                cx = lx
                for ch in line:
                    adv = font.getlength(ch)
                    if ch != " ":
                        chars.append(_Char(ch, cx, y, adv, idx, li))
                        idx += 1
                    cx += adv + tracking
                boxes.append((lx, y, lw, y + ascent))
            height = (len(lines) - 1) * line_h + ascent + descent
        lay = _Layout(chars, width, height, boxes, font, stroke, line_h)
        self._layout_cache[key] = lay
        return lay

    def block_origin(self, ctx: RenderContext, lay: _Layout) -> tuple[float, float]:
        x, y = self.x * ctx.scale, self.y * ctx.scale
        ox = {"left": x, "center": x - lay.width / 2, "right": x - lay.width}[self.align]
        oy = {"top": y, "middle": y - lay.height / 2, "bottom": y - lay.height}[self.valign]
        if self.safe_clamp and not self.rotation:
            sx0, sy0, sx1, sy1 = ctx.safe_rect()
            if lay.width <= sx1 - sx0:
                ox = min(max(ox, sx0), sx1 - lay.width)
            if lay.height <= sy1 - sy0:
                oy = min(max(oy, sy0), sy1 - lay.height)
        return ox, oy

    def bbox(self, ctx: RenderContext) -> tuple[int, int, int, int]:
        """Static (fully revealed) text box in output px: x0, y0, x1, y1."""
        lay = self.layout(ctx)
        ox, oy = self.block_origin(ctx, lay)
        return int(ox), int(oy), int(math.ceil(ox + lay.width)), int(math.ceil(oy + lay.height))

    # ---------- animation ----------
    def _char_state(self, c: _Char, n: int, t: float, line_h: float, sc: float):
        """-> (opacity, dx, dy, scale, rot) for one glyph at local time t."""
        op, dx, dy, s, rot = 1.0, 0.0, 0.0, 1.0, 0.0
        a = self.animation
        start = c.index * self.stagger
        if a in ("appear", "typewriter"):
            op = 1.0 if t >= start else 0.0
        elif a != "none":
            default_ease = {"bounce": "out_bounce", "slam": "out_expo", "scale": "out_back", "pop": "out_back",
                            "fly_in": "out_expo", "rotate": "out_back", "drop": "out_bounce"}.get(a, "out_cubic")
            p = easing.progress(t, start, self.char_duration, self.ease or default_ease)
            raw = easing.clamp01((t - start) / max(self.char_duration, 1e-6))
            q = 1 - p
            if a == "fade":
                op = p
            elif a in ("bounce", "drop"):
                dy = -line_h * 0.8 * q
                op = min(1.0, raw * 4)
            elif a == "rotate":
                rot, op = 90 * q, min(1.0, raw * 2)
            elif a == "fly_in":
                dy, op = 260 * sc * q, min(1.0, raw * 2)
            elif a == "slam":
                s, op = 1 + 2.2 * q, min(1.0, raw * 2.5)
            elif a in ("scale", "pop"):
                s, op = max(p, 0.0), min(1.0, raw * 3)
        if self.exit and self.exit_start is not None:
            es = self.exit_start + c.index * self.exit_stagger
            if t >= es:
                p = easing.progress(t, es, self.exit_duration, "in_cubic")
                if self.exit == "fade":
                    op *= 1 - p
                elif self.exit == "fly_out":
                    dy -= 220 * sc * p
                    op *= 1 - p
                elif self.exit == "scale_out":
                    s *= 1 - p
                elif self.exit == "drop":
                    dy += 300 * sc * p
                    op *= 1 - p
                elif self.exit == "typewriter":
                    # reverse order removal
                    es2 = self.exit_start + (n - 1 - c.index) * max(self.exit_stagger, 0.03)
                    op *= 0.0 if t >= es2 else 1.0
        return op, dx, dy, s, rot

    def last_char_done(self) -> float:
        n = max(len(self.text.replace("\n", "").replace(" ", "")), 1)
        return (n - 1) * self.stagger + (0 if self.animation in ("appear", "typewriter") else self.char_duration)

    # ---------- rendering ----------
    def render(self, ctx: RenderContext, t: float) -> Patch | None:
        lay = self.layout(ctx)
        if not lay.chars:
            return None
        ox, oy = self.block_origin(ctx, lay)
        placed = []  # (mask(h,w,2), x, y, opacity)
        n = len(lay.chars)
        for c in lay.chars:
            op, dx, dy, s, rot = self._char_state(c, n, t, lay.line_h, ctx.scale)
            if op <= 0.003 or s <= 0.01:
                continue
            mask, pad = _glyph(lay.font, c.ch, lay.stroke)
            gx, gy = ox + c.x - pad + dx, oy + c.y - pad + dy
            if abs(s - 1) > 1e-3 or abs(rot) > 1e-3:
                h, w = mask.shape[:2]
                m = cv2.getRotationMatrix2D((w / 2, h / 2), rot, s)
                corners = np.array([[0, 0, 1], [w, 0, 1], [0, h, 1], [w, h, 1]], np.float32) @ m.T
                mn, mx = np.floor(corners.min(0)), np.ceil(corners.max(0))
                m[:, 2] -= mn
                mask = cv2.warpAffine(mask, m, (int(mx[0] - mn[0]), int(mx[1] - mn[1])), flags=cv2.INTER_LINEAR)
                gx, gy = gx + mn[0], gy + mn[1]
            placed.append((mask, int(round(gx)), int(round(gy)), op))
        static = (int(math.floor(ox)), int(math.floor(oy)), int(math.ceil(ox + lay.width)), int(math.ceil(oy + lay.height)))
        ul_rects = self._underline_rects(ctx, t, lay, ox, oy)
        if not placed and not ul_rects:
            return None
        xs0 = [p[1] for p in placed] + [r[0] for r in ul_rects] + [static[0]]
        ys0 = [p[2] for p in placed] + [r[1] for r in ul_rects] + [static[1]]
        xs1 = [p[1] + p[0].shape[1] for p in placed] + [r[2] for r in ul_rects] + [static[2]]
        ys1 = [p[2] + p[0].shape[0] for p in placed] + [r[3] for r in ul_rects] + [static[3]]
        bx0, by0, bx1, by1 = min(xs0), min(ys0), max(xs1), max(ys1)
        bw, bh = bx1 - bx0, by1 - by0
        F = np.zeros((bh, bw), np.float32)
        S = np.zeros((bh, bw), np.float32)
        for mask, x, y, op in placed:
            h, w = mask.shape[:2]
            fx, fy = x - bx0, y - by0
            F[fy:fy + h, fx:fx + w] = np.maximum(F[fy:fy + h, fx:fx + w], mask[..., 0] * op)
            S[fy:fy + h, fx:fx + w] = np.maximum(S[fy:fy + h, fx:fx + w], mask[..., 1] * op)
        # fill colour (solid or gradient over the static text box)
        if self.gradient:
            # gradient is anchored to the static text box so it doesn't drift while glyphs move
            sw_, sh_ = max(static[2] - static[0], 1), max(static[3] - static[1], 1)
            a = math.radians(self.gradient.get("angle", 90))
            ys, xs = np.mgrid[0:bh, 0:bw].astype(np.float32)
            xs += bx0 - static[0] - sw_ / 2
            ys += by0 - static[1] - sh_ / 2
            span = abs(sw_ * math.cos(a)) + abs(sh_ * math.sin(a))
            p = np.clip((xs * math.cos(a) + ys * math.sin(a)) / max(span, 1e-6) + 0.5, 0, 1)[..., None]
            c0 = np.array(resolve_color(ctx.brand, self.gradient.get("from", "primary")), np.float32)
            c1 = np.array(resolve_color(ctx.brand, self.gradient.get("to", "secondary")), np.float32)
            fill_rgb = c0 * (1 - p) + c1 * p
        else:
            fill_rgb = np.empty((bh, bw, 3), np.float32)
            fill_rgb[:] = resolve_color(ctx.brand, self.color)
        if self.sweep:
            fill_rgb = self._apply_sweep(fill_rgb, t, static, bx0, by0, ctx)
        stroke_rgb = np.array(resolve_color(ctx.brand, self.stroke_color), np.float32)
        S = np.maximum(S, F) if lay.stroke > 0 else S
        A = F + S * (1 - F)
        rgb = (fill_rgb * F[..., None] + stroke_rgb * (S * (1 - F))[..., None]) / np.maximum(A, 1e-6)[..., None]
        rgba = np.dstack([rgb, A]).astype(np.float32)
        for (x0, y0, x1, y1, col) in ul_rects:
            rgba[y0 - by0:y1 - by0, x0 - bx0:x1 - bx0, :3] = col
            rgba[y0 - by0:y1 - by0, x0 - bx0:x1 - bx0, 3] = 1.0
        if self.mask_reveal:
            rgba[..., 3] *= self._reveal_mask(t, static, bx0, by0, bw, bh)
        patch = Patch(rgba, bx0, by0)
        if self.shadow:
            sh = self.shadow
            off = sh.get("offset", (0, 6))
            patch = canvas.drop_shadow(patch, resolve_hex(ctx.brand, sh.get("color", "#000000")), sh.get("opacity", 0.45),
                                       sh.get("blur", 8) * ctx.scale, (int(off[0] * ctx.scale), int(off[1] * ctx.scale)))
        if self.rotation:
            patch = canvas.transform_patch(patch, 1.0, self.rotation, anchor=(self.x * ctx.scale, self.y * ctx.scale))
        return patch

    def _underline_rects(self, ctx, t, lay, ox, oy):
        u = self.underline
        if not u or self.vertical:
            return []
        p = easing.progress(t, u.get("start", self.last_char_done()), u.get("duration", 0.4), u.get("ease", "out_expo"))
        if p <= 0:
            return []
        th = max(int(round(u.get("thickness", 8) * ctx.scale)), 1)
        off = u.get("offset", 14) * ctx.scale
        col = np.array(resolve_color(ctx.brand, u.get("color", "accent")), np.float32)
        rects = []
        _, descent = lay.font.getmetrics()
        for (lx, ly, lw, baseline) in lay.line_boxes:
            x0 = int(ox + lx)
            y0 = int(oy + baseline + off)
            x1 = int(ox + lx + lw * p)
            if x1 > x0:
                rects.append((x0, y0, x1, y0 + th, col))
        return rects

    def _apply_sweep(self, fill_rgb, t, static, bx0, by0, ctx):
        sw = self.sweep
        dur = sw.get("duration", 0.7)
        p = (t - sw.get("start", self.last_char_done())) / dur
        if p < 0 or p > 1:
            return fill_rgb
        h, w = fill_rgb.shape[:2]
        band = sw.get("width", 120) * ctx.scale
        sx0, sx1 = static[0] - bx0, static[2] - bx0
        centre = sx0 - band + (sx1 - sx0 + 2 * band) * easing.in_out_sine(p)
        ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
        d = (xs + ys * 0.35) - centre   # slanted band
        m = np.clip(1 - np.abs(d) / max(band / 2, 1), 0, 1) ** 2 * sw.get("intensity", 0.85)
        col = np.array(resolve_color(ctx.brand, sw.get("color", "#FFFFFF")), np.float32)
        return fill_rgb + (col - fill_rgb) * m[..., None]

    def _reveal_mask(self, t, static, bx0, by0, bw, bh):
        mr = self.mask_reveal
        p = easing.progress(t, mr.get("start", 0.0), mr.get("duration", 0.6), mr.get("ease", "out_expo"))
        d = mr.get("direction", "left")  # direction the reveal travels from
        ys, xs = np.mgrid[0:bh, 0:bw].astype(np.float32)
        sx0, sy0, sx1, sy1 = static[0] - bx0, static[1] - by0, static[2] - bx0, static[3] - by0
        soft = 6.0
        if d == "left":
            edge = sx0 + (sx1 - sx0 + soft) * p
            return np.clip((edge - xs) / soft, 0, 1)
        if d == "right":
            edge = sx1 - (sx1 - sx0 + soft) * p
            return np.clip((xs - edge) / soft, 0, 1)
        if d == "up":   # rises from the bottom
            edge = sy1 - (sy1 - sy0 + soft) * p
            return np.clip((ys - edge) / soft, 0, 1)
        edge = sy0 + (sy1 - sy0 + soft) * p
        return np.clip((edge - ys) / soft, 0, 1)


def resolve_hex(brand, color) -> str:
    r, g, b = resolve_color(brand, color)
    return "#%02X%02X%02X" % (round(r * 255), round(g * 255), round(b * 255))


def text_patch(text: str, ctx: RenderContext, **kw) -> Patch | None:
    """One-shot static text render (fully revealed) — useful for cards and tests."""
    kw.setdefault("animation", "none")
    return TextLayer(text, **kw).render(ctx, 1e6 if kw.get("exit") is None else 0.0)


class WordHighlightLayer(Layer):
    """Subtitle line with the currently spoken word highlighted (karaoke style).

    words = [{"text": "創業", "start": 0.0, "end": 0.4}, ...] with times local to the layer.
    style: highlight colour, optional pill behind the active word, pop scale on the active word.
    This is the *visual* style only; timing comes from the transcription / subtitle engine.
    """

    def __init__(self, words: list[dict], x: float = 540, y: float = 1380, size: float = 66, role: str = "subtitle",
                 color="#FFFFFF", highlight_color="accent", pill_color=None, stroke: float = 7,
                 stroke_color="#000000", max_width: float = 860, line_spacing: float = 1.3, pop: float = 1.12,
                 gap: float = 0.0, **kw):
        if kw.get("duration") is None and words:
            kw["duration"] = max(w["end"] for w in words)
        super().__init__(**kw)
        self.words, self.x, self.y, self.size, self.role = words, x, y, size, role
        self.color, self.highlight_color, self.pill_color = color, highlight_color, pill_color
        self.stroke, self.stroke_color, self.max_width, self.line_spacing = stroke, stroke_color, max_width, line_spacing
        self.pop, self.gap = pop, gap
        self._cache: dict = {}

    def _word_patch(self, ctx, text, active):
        key = (text, active, ctx.scale, id(ctx.brand))
        if key not in self._cache:
            self._cache[key] = TextLayer(text, x=0, y=0, size=self.size, role=self.role, align="left",
                                         color=self.highlight_color if active else self.color, stroke=self.stroke,
                                         stroke_color=self.stroke_color, animation="none", safe_clamp=False,
                                         shadow={"blur": 6, "opacity": 0.4, "offset": (0, 3)}).render(ctx, 0)
        return self._cache[key]

    def _layout(self, ctx):
        key = ("layout", ctx.scale, id(ctx.brand))
        if key not in self._cache:
            font = get_font(ctx.brand, self.role, ctx.px(self.size))
            gap = ctx.px(self.gap) + (font.getlength(" ") if any(not is_cjk(w["text"][0]) for w in self.words) else 0)
            maxw = self.max_width * ctx.scale
            lines, cur, cur_w = [], [], 0.0
            for i, w in enumerate(self.words):
                ww = font.getlength(w["text"])
                if cur and cur_w + gap + ww > maxw:
                    lines.append((cur, cur_w))
                    cur, cur_w = [], 0.0
                cur_w += (gap if cur else 0) + ww
                cur.append((i, ww))
            if cur:
                lines.append((cur, cur_w))
            ascent, descent = font.getmetrics()
            lh = (ascent + descent) * self.line_spacing
            pos = {}
            for li, (items, lw) in enumerate(lines):
                x = self.x * ctx.scale - lw / 2
                for i, ww in items:
                    pos[i] = (x, self.y * ctx.scale + li * lh, ww)
                    x += ww + gap
            self._cache[key] = (pos, ascent + descent)
        return self._cache[key]

    def render(self, ctx, t):
        pos, lh = self._layout(ctx)
        group = None
        from ._util import over  # local import keeps module import order simple
        patches = []
        for i, w in enumerate(self.words):
            active = w["start"] <= t < w["end"]
            p = self._word_patch(ctx, w["text"], active)
            if p is None:
                continue
            x, y, ww = pos[i]
            pp = Patch(p.rgba, int(x + p.x), int(y + p.y))
            if active:
                prog = easing.progress(t, w["start"], 0.12, "out_back")
                s = 1 + (self.pop - 1) * prog
                pp = canvas.transform_patch(pp, s, 0.0, anchor=(x + ww / 2, y + lh / 2))
                if self.pill_color:
                    pad = ctx.px(14)
                    pill = np.zeros((int(lh + pad), int(ww * s + 2 * pad), 4), np.float32)
                    from ._util import rounded_rect_mask
                    pill[..., :3] = resolve_color(ctx.brand, self.pill_color)
                    pill[..., 3] = rounded_rect_mask(pill.shape[1], pill.shape[0], pad * 1.2)
                    patches.append(Patch(pill, int(x + ww / 2 - pill.shape[1] / 2), int(y + lh / 2 - pill.shape[0] / 2)))
            patches.append(pp)
        if not patches:
            return None
        x0 = min(p.x for p in patches); y0 = min(p.y for p in patches)
        x1 = max(p.x + p.w for p in patches); y1 = max(p.y + p.h for p in patches)
        group = Patch(np.zeros((y1 - y0, x1 - x0, 4), np.float32), x0, y0)
        for p in patches:
            over(group, p)
        return group
