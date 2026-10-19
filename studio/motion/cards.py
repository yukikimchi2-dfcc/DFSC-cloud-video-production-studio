"""Motion cards: panels with text that animate in/out as one unit.

Every card takes a rect in design px (x, y = top-left, w, h), a colour (brand key or hex),
timing (enter / enter_duration / exit / exit_start / exit_duration / ease), z and safe-area clamp.
Card content (TextLayers etc.) is rendered at the card's local time and moved with the card.
"""
from __future__ import annotations

import math

import cv2
import numpy as np

from studio.core import canvas, easing, vector
from studio.core.canvas import Patch
from studio.core.timeline import Layer, RenderContext

from ._util import (enter_exit_state, linear_gradient, offset, over, resolve_color, rounded_rect_mask,
                    solid_patch, with_opacity)
from .typography import TextLayer


class Card(Layer):
    """Base card: solid rounded panel + child layers. Subclasses override `panel()` / `children()`."""

    def __init__(self, x: float = 90, y: float = 1200, w: float = 900, h: float = 300, color="primary",
                 radius: float = 28, panel_opacity: float = 1.0, border: dict | None = None,
                 enter: str = "slide_up", enter_duration: float = 0.5, exit: str | None = "fade",
                 exit_start: float | None = None, exit_duration: float = 0.35, ease: str | None = None,
                 safe_clamp: bool = True, shadow: dict | None = None, content: list[Layer] | None = None, **kw):
        super().__init__(**kw)
        self.x, self.y, self.w, self.h = x, y, w, h
        self.color, self.radius, self.panel_opacity, self.border = color, radius, panel_opacity, border
        self.enter, self.enter_duration, self.exit, self.exit_duration, self.ease = enter, enter_duration, exit, exit_duration, ease
        self.exit_start = exit_start
        if exit and exit_start is None and self.duration is not None:
            self.exit_start = max(self.duration - exit_duration, 0)
        self.safe_clamp, self.shadow = safe_clamp, shadow
        self.content = content or []

    # rect in output px after safe-area clamping
    def rect(self, ctx: RenderContext) -> tuple[int, int, int, int]:
        x, y, w, h = ctx.px(self.x), ctx.px(self.y), max(ctx.px(self.w), 1), max(ctx.px(self.h), 1)
        if self.safe_clamp:
            sx0, sy0, sx1, sy1 = ctx.safe_rect()
            if w <= sx1 - sx0:
                x = min(max(x, sx0), sx1 - w)
            if h <= sy1 - sy0:
                y = min(max(y, sy0), sy1 - h)
        return x, y, w, h

    def state(self, t: float):
        return enter_exit_state(t, self.enter, self.enter_duration, self.exit, self.exit_start,
                                self.exit_duration, self.ease)

    def panel(self, ctx: RenderContext, t: float, w: int, h: int, reveal: float) -> Patch | None:
        mask = rounded_rect_mask(w, h, self.radius * ctx.scale)
        p = solid_patch(w, h, resolve_color(ctx.brand, self.color), mask * self.panel_opacity)
        self._border(ctx, p, w, h)
        return p

    def _border(self, ctx, p: Patch, w: int, h: int) -> None:
        if not self.border:
            return
        th = max(int(round(self.border.get("width", 2) * ctx.scale)), 1)
        outer = rounded_rect_mask(w, h, self.radius * ctx.scale)
        inner = np.zeros_like(outer)
        inner[th:h - th, th:w - th] = rounded_rect_mask(w - 2 * th, h - 2 * th, max(self.radius * ctx.scale - th, 0))
        ring = np.clip(outer - inner, 0, 1) * self.border.get("opacity", 1.0)
        col = np.array(resolve_color(ctx.brand, self.border.get("color", "#FFFFFF")), np.float32)
        a = p.rgba[..., 3:4]
        r = ring[..., None]
        na = r + a * (1 - r)
        p.rgba[..., :3] = (col * r + p.rgba[..., :3] * a * (1 - r)) / np.maximum(na, 1e-6)
        p.rgba[..., 3:4] = na

    def children(self, ctx: RenderContext, t: float) -> list[Layer]:
        return self.content

    def _content_time(self, t: float) -> float:
        return t - self.enter_duration * 0.4  # content starts while the panel is still settling

    def compose(self, ctx: RenderContext, t: float) -> Patch | None:
        """Panel + children in frame coordinates, before the card-level transform."""
        x, y, w, h = self.rect(ctx)
        st = self.state(t)
        vis_w = max(int(round(w * st.reveal)), 1) if st.reveal < 1 else w
        panel = self.panel(ctx, t, vis_w, h, st.reveal)
        group = Patch(np.zeros((h, w, 4), np.float32), x, y)
        if panel is not None:
            panel.x, panel.y = x + (w - vis_w) // 2, y
            over(group, panel)
        ct = self._content_time(t)
        for child in self.children(ctx, t):
            if child.start <= ct < child.end:
                cp = child.render(ctx, ct - child.start)
                if cp is not None:
                    group = _union_over(group, cp, child.opacity)
        if st.reveal < 1:  # expanding cards clip their content to the visible panel
            cx0 = (w - vis_w) // 2 + (x - group.x)
            group.rgba[:, :max(cx0, 0), 3] = 0
            group.rgba[:, cx0 + vis_w:, 3] = 0
        return group

    def render(self, ctx: RenderContext, t: float) -> Patch | None:
        patch = self.compose(ctx, t)
        if patch is None:
            return None
        st = self.state(t)
        if self.shadow:
            sh = self.shadow
            patch = canvas.drop_shadow(patch, sh.get("color", "#000000"), sh.get("opacity", 0.35),
                                       sh.get("blur", 18) * ctx.scale, (0, int(sh.get("offset", 10) * ctx.scale)))
        patch = canvas.transform_patch(patch, st.scale, st.rotation)
        patch = offset(patch, st.dx * ctx.scale, st.dy * ctx.scale)
        return with_opacity(patch, st.opacity)


def _union_over(dst: Patch, src: Patch, opacity: float = 1.0) -> Patch:
    """Grow `dst` to contain `src` if needed, then composite src over it."""
    x0, y0 = min(dst.x, src.x), min(dst.y, src.y)
    x1, y1 = max(dst.x + dst.w, src.x + src.w), max(dst.y + dst.h, src.y + src.h)
    if (x0, y0, x1, y1) != (dst.x, dst.y, dst.x + dst.w, dst.y + dst.h):
        big = Patch(np.zeros((y1 - y0, x1 - x0, 4), np.float32), x0, y0)
        big.rgba[dst.y - y0:dst.y - y0 + dst.h, dst.x - x0:dst.x - x0 + dst.w] = dst.rgba
        dst = big
    return over(dst, src, opacity)


class SolidPanel(Card):
    pass


class GradientPanel(Card):
    def __init__(self, color_from="primary", color_to="secondary", angle: float = 90, **kw):
        super().__init__(**kw)
        self.color_from, self.color_to, self.angle = color_from, color_to, angle

    def panel(self, ctx, t, w, h, reveal):
        g = linear_gradient(w, h, resolve_color(ctx.brand, self.color_from), resolve_color(ctx.brand, self.color_to), self.angle)
        p = Patch(np.dstack([g, rounded_rect_mask(w, h, self.radius * ctx.scale) * self.panel_opacity]))
        self._border(ctx, p, w, h)
        return p


class GlassPanel(Card):
    """Frosted glass: blurs and tints whatever is underneath, with a light border."""

    def __init__(self, blur: float = 24, tint="#FFFFFF", tint_opacity: float = 0.18, **kw):
        kw.setdefault("border", {"color": "#FFFFFF", "width": 2, "opacity": 0.45})
        super().__init__(**kw)
        self.blur, self.tint, self.tint_opacity = blur, tint, tint_opacity
        self._frame: np.ndarray | None = None

    def draw(self, frame, ctx, t):
        self._frame = frame
        return super().draw(frame, ctx, t)

    def panel(self, ctx, t, w, h, reveal):
        x, y, fw, fh = self.rect(ctx)
        st = self.state(t)
        px = x + (fw - w) // 2 + int(st.dx * ctx.scale)
        py = y + int(st.dy * ctx.scale)
        H, W = (self._frame.shape[:2] if self._frame is not None else (ctx.height, ctx.width))
        region = np.zeros((h, w, 3), np.float32)
        if self._frame is not None:
            pad = int(self.blur * ctx.scale * 2)
            sx0, sy0 = max(px - pad, 0), max(py - pad, 0)
            sx1, sy1 = min(px + w + pad, W), min(py + h + pad, H)
            if sx1 > sx0 and sy1 > sy0:
                src = self._frame[sy0:sy1, sx0:sx1]
                k = int(self.blur * ctx.scale) * 2 + 1
                blurred = cv2.GaussianBlur(src, (k, k), self.blur * ctx.scale)
                ox, oy = px - sx0, py - sy0
                bx0, by0 = max(ox, 0), max(oy, 0)
                bx1, by1 = min(ox + w, blurred.shape[1]), min(oy + h, blurred.shape[0])
                if bx1 > bx0 and by1 > by0:
                    region[by0 - oy:by1 - oy, bx0 - ox:bx1 - ox] = blurred[by0:by1, bx0:bx1]
        tint = np.array(resolve_color(ctx.brand, self.tint), np.float32)
        rgb = region * (1 - self.tint_opacity) + tint * self.tint_opacity
        p = Patch(np.dstack([rgb, rounded_rect_mask(w, h, self.radius * ctx.scale) * self.panel_opacity]))
        self._border(ctx, p, w, h)
        return p


class ExpandableTitleCard(Card):
    """Panel grows horizontally from the centre, then the title types in."""

    def __init__(self, title: str, subtitle: str | None = None, text_color="text", title_size: float = 84,
                 subtitle_size: float = 44, **kw):
        kw.setdefault("enter", "expand")
        kw.setdefault("enter_duration", 0.55)
        kw.setdefault("ease", "out_expo")
        super().__init__(**kw)
        self.title, self.subtitle, self.text_color = title, subtitle, text_color
        self.title_size, self.subtitle_size = title_size, subtitle_size

    def _content_time(self, t):
        return t - self.enter_duration * 0.8

    def children(self, ctx, t):
        if not hasattr(self, "_kids"):
            cx = self.x + self.w / 2
            ty = self.y + self.h / 2 - (self.title_size * 0.62 if self.subtitle else 0)
            kids = [TextLayer(self.title, x=cx, y=ty, size=self.title_size, role="title", color=self.text_color,
                              valign="middle", animation="fly_in", stagger=0.035, max_width=self.w * 0.9, safe_clamp=False)]
            if self.subtitle:
                kids.append(TextLayer(self.subtitle, x=cx, y=ty + self.title_size * 0.75, size=self.subtitle_size,
                                      role="body", color=self.text_color, animation="fade", start=0.25,
                                      max_width=self.w * 0.9, safe_clamp=False))
            self._kids = kids
        return self._kids


class ImpactCard(Card):
    """Big slammed typography on a block, with a quick scale punch."""

    def __init__(self, text: str, text_color="text", size: float = 150, stroke: float = 0, **kw):
        kw.setdefault("enter", "slam")
        kw.setdefault("enter_duration", 0.35)
        super().__init__(**kw)
        self._kid = TextLayer(text, x=self.x + self.w / 2, y=self.y + self.h / 2, size=size, role="title",
                              color=text_color, valign="middle", animation="slam", stagger=0.05, stroke=stroke,
                              max_width=self.w * 0.92, safe_clamp=False)

    def _content_time(self, t):
        return t

    def children(self, ctx, t):
        return [self._kid]


class StatCard(Card):
    """Counting number (e.g. 0 -> 1,200) with a prefix/suffix and a label underneath."""

    def __init__(self, value: float, label: str = "", prefix: str = "", suffix: str = "", decimals: int = 0,
                 count_duration: float = 1.2, number_size: float = 170, label_size: float = 46,
                 number_color="text", label_color="text", **kw):
        super().__init__(**kw)
        self.value, self.label, self.prefix, self.suffix, self.decimals = value, label, prefix, suffix, decimals
        self.count_duration, self.number_size, self.label_size = count_duration, number_size, label_size
        self.number_color, self.label_color = number_color, label_color
        self._label = TextLayer(label, x=self.x + self.w / 2, y=self.y + self.h * 0.72, size=label_size, role="body",
                                color=label_color, valign="middle", animation="fade", start=0.3,
                                max_width=self.w * 0.9, safe_clamp=False) if label else None
        self._num_cache: dict[str, TextLayer] = {}

    def number_text(self, t: float) -> str:
        p = easing.progress(t, 0, self.count_duration, "out_expo")
        v = self.value * p
        body = f"{v:,.{self.decimals}f}"
        return f"{self.prefix}{body}{self.suffix}"

    def children(self, ctx, t):
        txt = self.number_text(max(self._content_time(t), 0))
        if txt not in self._num_cache:
            if len(self._num_cache) > 400:
                self._num_cache.clear()
            self._num_cache[txt] = TextLayer(txt, x=self.x + self.w / 2, y=self.y + self.h * 0.38,
                                             size=self.number_size, role="title", color=self.number_color,
                                             valign="middle", animation="none", safe_clamp=False)
        return [self._num_cache[txt]] + ([self._label] if self._label else [])


class QuoteCard(Card):
    def __init__(self, quote: str, author: str = "", text_color="text", accent="accent", quote_size: float = 58, **kw):
        super().__init__(**kw)
        self.kids = [
            TextLayer("「", x=self.x + 50, y=self.y + 20, size=quote_size * 2.2, role="title", color=accent,
                      align="left", animation="pop", safe_clamp=False),
            TextLayer(quote, x=self.x + self.w / 2, y=self.y + self.h * 0.28, size=quote_size, role="body",
                      color=text_color, animation="typewriter", stagger=0.045, max_width=self.w * 0.8,
                      line_spacing=1.35, start=0.15, safe_clamp=False),
        ]
        if author:
            self.kids.append(TextLayer(f"— {author}", x=self.x + self.w - 60, y=self.y + self.h - 100,
                                       size=quote_size * 0.7, role="body", color=accent, align="right",
                                       animation="fade", start=0.15 + len(quote) * 0.045, safe_clamp=False))

    def children(self, ctx, t):
        return self.kids


class CTACard(Card):
    """Call-to-action pill with an arrow and a gentle pulse once it lands."""

    def __init__(self, text: str = "立即報名", sub: str | None = None, text_color="text", button_color="secondary",
                 pulse: float = 0.04, **kw):
        kw.setdefault("enter", "pop")
        kw.setdefault("radius", 999)
        kw.setdefault("color", button_color)
        super().__init__(**kw)
        self.pulse = pulse
        self.kids = [TextLayer(f"{text}  →", x=self.x + self.w / 2, y=self.y + self.h / 2, size=self.h * 0.42,
                               role="title", color=text_color, valign="middle", animation="none", safe_clamp=False)]
        if sub:
            self.kids.append(TextLayer(sub, x=self.x + self.w / 2, y=self.y + self.h + 28, size=40, role="body",
                                       color=text_color, animation="fade", start=0.3, safe_clamp=False))

    def children(self, ctx, t):
        return self.kids

    def state(self, t):
        st = super().state(t)
        if t > self.enter_duration:
            st.scale *= 1 + self.pulse * (0.5 - 0.5 * math.cos(2 * math.pi * (t - self.enter_duration) / 1.1))
        return st


class BrandLockupCard(Card):
    """Brand logo (vector shape from the brand kit) scaling in, optional tagline underneath."""

    def __init__(self, logo: str = "dfsc_lockup", logo_height: float = 260, tagline: str | None = None,
                 tagline_color="text", logo_colors: dict | None = None, panel: bool = False, **kw):
        kw.setdefault("enter", "pop")
        kw.setdefault("enter_duration", 0.6)
        super().__init__(**kw)
        self.logo, self.logo_height, self.tagline = logo, logo_height, tagline
        self.tagline_color, self.logo_colors, self.show_panel = tagline_color, logo_colors, panel
        self._shape_cache: dict = {}

    def panel(self, ctx, t, w, h, reveal):
        base = super().panel(ctx, t, w, h, reveal) if self.show_panel else Patch(np.zeros((h, w, 4), np.float32))
        key = (ctx.brand.project_id if ctx.brand else None, ctx.px(self.logo_height))
        if key not in self._shape_cache:
            shape = ctx.brand.logo_shape(self.logo) if ctx.brand and self.logo in ctx.brand.logos else vector.star_shape()
            lp = vector.render_shape(shape, ctx.px(self.logo_height), colors=self.logo_colors)
            if lp.w > w * 0.92:  # wide lockups: fit width
                lp = vector.render_shape(shape, max(int(ctx.px(self.logo_height) * w * 0.92 / lp.w), 1), colors=self.logo_colors)
            self._shape_cache[key] = lp
        lp = self._shape_cache[key]
        lp = Patch(lp.rgba, (w - lp.w) // 2, int(h * (0.42 if self.tagline else 0.5)) - lp.h // 2)
        over(base, lp)
        return base

    def children(self, ctx, t):
        if not self.tagline:
            return []
        if not hasattr(self, "_kid"):
            self._kid = TextLayer(self.tagline, x=self.x + self.w / 2, y=self.y + self.h * 0.78, size=48, role="body",
                                  color=self.tagline_color, animation="fade", stagger=0.02, start=0.2,
                                  valign="middle", safe_clamp=False, max_width=self.w * 0.9)
        return [self._kid]
