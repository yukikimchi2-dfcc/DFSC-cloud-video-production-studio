"""DFSC components rebuilt from the edited reference videos (two separate families).

Interview reel  — DFCC_9Oct_ChiliAng_Eggteen.mp4 / DFCC_YYLim_QJoyBalloon.mp4 / DFCC_9Oct_JoshuaChin_SmartRental.mov
Launch cinematic — Facebook 1078068961776091 (第11屆啟航宣傳片)
Exact sources (file + timecode + what was measured): projects/dfsc-2027/references/TEMPLATE_SOURCES.md.

Geometry is in 1080x1920 design pixels (ctx.px scales to the output). Colours come from the brand kit
keys `ref_*`, which were sampled from reference pixels. Text markup: [keyword] = highlighted word.
"""
from __future__ import annotations

import math
import re

import cv2
import numpy as np
from PIL import Image, ImageDraw

from studio.core import canvas, easing, vector
from studio.core.canvas import Patch
from studio.core.timeline import Layer

from ._util import get_font, linear_gradient, resolve_color
from .stickers import add_outline, emoji_image

_MARK = re.compile(r"\[([^\]]+)\]")


def parse_marked(text: str) -> list[tuple[str, bool]]:
    """'在還沒有參加[圓夢]之前' -> [('在還沒有參加', False), ('圓夢', True), ('之前', False)]"""
    out, pos = [], 0
    for m in _MARK.finditer(text):
        if m.start() > pos:
            out.append((text[pos:m.start()], False))
        out.append((m.group(1), True))
        pos = m.end()
    if pos < len(text):
        out.append((text[pos:], False))
    return [s for s in out if s[0]]


def _rgb255(brand, color) -> tuple[int, int, int]:
    return tuple(int(round(c * 255)) for c in resolve_color(brand, color))


def text_patch(brand, text: str, role: str, size: int, color="#FFFFFF", highlight="#6CD76B",
               stroke: int = 0, stroke_color="#000000", underline: bool = False, tracking: float = 0.0,
               shadow: int = 0) -> Patch:
    """Single line of marked text rendered with PIL; returns a tight RGBA patch at (0, 0)."""
    font = get_font(brand, role, size)
    segs = parse_marked(text)
    pad = stroke + shadow + 4
    widths = []
    for s, _ in segs:
        widths.append(sum(font.getlength(ch) + size * tracking for ch in s) if tracking else font.getlength(s))
    asc, desc = font.getmetrics()
    w = int(sum(widths)) + 2 * pad
    h = asc + desc + 2 * pad + (int(size * 0.12) if underline else 0)
    img = Image.new("RGBA", (max(w, 1), max(h, 1)), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    x = pad
    for (s, hi), sw in zip(segs, widths):
        fill = _rgb255(brand, highlight if hi else color) + (255,)
        cx = x
        for ch in (s if tracking else [s]):
            if shadow:
                d.text((cx + shadow, pad + shadow), ch, font=font, fill=(0, 0, 0, 110),
                       stroke_width=stroke, stroke_fill=(0, 0, 0, 110))
            d.text((cx, pad), ch, font=font, fill=fill, stroke_width=stroke,
                   stroke_fill=_rgb255(brand, stroke_color) + (255,))
            cx += font.getlength(ch) + size * tracking if tracking else sw
        if hi and underline:
            y = pad + asc + int(size * 0.06)
            d.rectangle([x, y, x + sw, y + max(int(size * 0.08), 2)], fill=fill)
        x += sw
    return Patch(np.asarray(img, np.float32) / 255)


def paste(dst: np.ndarray, src: np.ndarray, x: int, y: int) -> np.ndarray:
    """In-place straight-alpha 'over' of RGBA `src` onto RGBA `dst` at (x, y), clipped to dst."""
    H, W = dst.shape[:2]
    x0, y0, x1, y1 = max(x, 0), max(y, 0), min(x + src.shape[1], W), min(y + src.shape[0], H)
    if x0 >= x1 or y0 >= y1:
        return dst
    s = src[y0 - y:y1 - y, x0 - x:x1 - x]
    d = dst[y0:y1, x0:x1]
    sa, da = s[..., 3:4], d[..., 3:4]
    oa = sa + da * (1 - sa)
    rgb = (s[..., :3] * sa + d[..., :3] * da * (1 - sa)) / np.maximum(oa, 1e-6)
    d[..., :3], d[..., 3:4] = rgb, oa
    return dst


def _grad_rect(brand, w: int, h: int, top, bottom, border=None, border_px: int = 0) -> np.ndarray:
    rgba = np.ones((h, w, 4), np.float32)
    rgba[..., :3] = linear_gradient(w, h, resolve_color(brand, top), resolve_color(brand, bottom), 90)
    if border and border_px:
        b = np.array(resolve_color(brand, border), np.float32)
        rgba[:border_px, :, :3] = b
        rgba[-border_px:, :, :3] = b
        rgba[:, :border_px, :3] = b
        rgba[:, -border_px:, :3] = b
    return rgba


def _sticker(char: str, height: int) -> np.ndarray:
    img = emoji_image(char)
    s = height / img.shape[0]
    img = cv2.resize(img, (max(int(img.shape[1] * s), 1), height), interpolation=cv2.INTER_AREA)
    return add_outline(img, max(height // 16, 3))


def _pop(t: float, dur: float = 0.25) -> tuple[float, float]:
    """Reference labels cut in with a short scale pop (≈0.2 s at 60 fps): returns (scale, alpha)."""
    k = easing.progress(t, 0, dur, "out_back")
    return 0.85 + 0.15 * k, min(1.0, t / (dur * 0.6))


def _place(frame, patch: Patch, ctx, cx: float, cy: float, scale: float = 1.0, alpha: float = 1.0):
    """Composite a design-space patch centred at (cx, cy) design px."""
    s = ctx.scale * scale
    if s <= 0 or alpha <= 0:
        return frame
    rgba = patch.rgba
    if abs(s - 1) > 1e-3:
        rgba = cv2.resize(rgba, (max(int(rgba.shape[1] * s), 1), max(int(rgba.shape[0] * s), 1)),
                          interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR)
    p = Patch(rgba, int(ctx.px(cx) - rgba.shape[1] / 2), int(ctx.px(cy) - rgba.shape[0] / 2))
    return canvas.composite(frame, p, alpha)


class _CachedLayer(Layer):
    """Layer whose artwork is built once in design space (1080x1920) and placed per frame."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self._art: Patch | None = None

    def art(self, ctx) -> Patch:  # pragma: no cover - interface
        raise NotImplementedError

    def _get(self, ctx) -> Patch:
        if self._art is None:
            self._art = self.art(ctx)
        return self._art


# ============================================================== interview reel family

class InterviewTopLabel(_CachedLayer):
    """Navy gradient bar, square corners, thin border, white heavy text with green keywords,
    optional emoji sticker overlapping the right end. Ref: ChiliAng 0:00.5 (x 96–986, y 305–445)."""

    def __init__(self, text: str, y: float = 375, size: int = 96, sticker: str | None = None,
                 min_width: int = 0, **kw):
        super().__init__(**kw)
        self.text, self.y, self.size, self.sticker, self.min_width = text, y, size, sticker, min_width

    def art(self, ctx):
        b = ctx.brand
        t = text_patch(b, self.text, "title", self.size, "#FFFFFF", b.color("ref_keyword_green"), shadow=3)
        w = max(t.w + 120, self.min_width)
        h = int(self.size * 1.45)
        bar = _grad_rect(b, w, h, b.color("ref_label_navy_top"), b.color("ref_label_navy_bottom"),
                         b.color("ref_label_border"), 2)
        out = Patch(bar)
        canvas.composite(out.rgba[..., :3], Patch(t.rgba, (w - t.w) // 2, (h - t.h) // 2))  # text onto bar
        art = np.zeros((h + 60, w + 140, 4), np.float32)
        paste(art, out.rgba, 20, 30)
        if self.sticker:
            st = _sticker(self.sticker, int(h * 1.15))
            paste(art, st, 20 + w - st.shape[1] // 2, 30 + h // 2 - st.shape[0] // 2)
        return Patch(art)

    def draw(self, frame, ctx, t):
        s, a = _pop(t)
        return _place(frame, self._get(ctx), ctx, 540 + 50, self.y, s, a * self.opacity)


class InterviewSmallLabel(_CachedLayer):
    """Small navy tag above a big title, e.g. 「參加圓夢之前」. Ref: ChiliAng 0:04."""

    def __init__(self, text: str, y: float = 260, size: int = 44, **kw):
        super().__init__(**kw)
        self.text, self.y, self.size = text, y, size

    def art(self, ctx):
        b = ctx.brand
        t = text_patch(b, self.text, "heading", self.size, "#FFFFFF", b.color("ref_keyword_green"))
        w, h = t.w + 48, int(self.size * 1.6)
        bar = Patch(_grad_rect(b, w, h, b.color("ref_label_navy_top"), b.color("ref_label_navy_bottom"),
                               b.color("ref_label_border"), 2))
        canvas.composite(bar.rgba[..., :3], Patch(t.rgba, (w - t.w) // 2, (h - t.h) // 2))
        return bar

    def draw(self, frame, ctx, t):
        s, a = _pop(t)
        return _place(frame, self._get(ctx), ctx, 540, self.y, s, a * self.opacity)


class InterviewBigTitle(_CachedLayer):
    """Huge black heavy-serif words with a thick white outline (+ optional emoji). Ref: ChiliAng 0:04 「只有想法」."""

    def __init__(self, text: str, y: float = 420, size: int = 190, sticker: str | None = None, **kw):
        super().__init__(**kw)
        self.text, self.y, self.size, self.sticker = text, y, size, sticker

    def art(self, ctx):
        b = ctx.brand
        t = text_patch(b, self.text, "serif_title", self.size, "#111111", "#111111",
                       stroke=max(self.size // 14, 6), stroke_color="#FFFFFF")
        if not self.sticker:
            return t
        st = _sticker(self.sticker, int(self.size * 0.7))
        art = np.zeros((max(t.h, st.shape[0]), t.w + st.shape[1], 4), np.float32)
        paste(art, t.rgba, 0, 0)
        paste(art, st, t.w - 10, 0)
        return Patch(art)

    def draw(self, frame, ctx, t):
        s, a = _pop(t, 0.3)
        return _place(frame, self._get(ctx), ctx, 540, self.y, s, a * self.opacity)


class InterviewNameTag(_CachedLayer):
    """Green gradient name plate, square corners, white heavy text, stickers at both ends.
    Ref: ChiliAng 0:06 「Chili Ang」 (y 226–413)."""

    def __init__(self, name: str, y: float = 320, size: int = 110, left_sticker: str | None = None,
                 right_sticker: str | None = None, **kw):
        super().__init__(**kw)
        self.name, self.y, self.size = name, y, size
        self.left, self.right = left_sticker, right_sticker

    def art(self, ctx):
        b = ctx.brand
        t = text_patch(b, self.name, "title", self.size, "#FFFFFF", "#FFFFFF", shadow=4)
        w, h = t.w + 140, int(self.size * 1.7)
        plate = Patch(_grad_rect(b, w, h, b.color("ref_name_green_top"), b.color("ref_name_green_bottom")))
        canvas.composite(plate.rgba[..., :3], Patch(t.rgba, (w - t.w) // 2, (h - t.h) // 2))
        sh = int(h * 0.75)
        art = np.zeros((h + sh, w + 2 * sh, 4), np.float32)
        ox, oy = sh, sh // 3
        paste(art, plate.rgba, ox, oy)
        for char, x, y in ((self.left, ox - sh // 2, oy + h - sh // 2), (self.right, ox + w - sh // 2, 0)):
            if char:
                paste(art, _sticker(char, sh), x, y)
        return Patch(art)

    def draw(self, frame, ctx, t):
        s, a = _pop(t)
        return _place(frame, self._get(ctx), ctx, 540, self.y, s, a * self.opacity)


class InterviewSubtitle(Layer):
    """Bottom subtitles: white heavy sans, black outline, [keywords] green with underline bar.
    Ref: ChiliAng 0:00.5 — glyph rows y 1267–1326 → centre ≈1296, cap height ≈60 px."""

    def __init__(self, cues: list[tuple[float, float, str]], y: float = 1296, size: int = 66, **kw):
        kw.setdefault("duration", max((e for _, e, _ in cues), default=0))
        super().__init__(**kw)
        self.cues, self.y, self.size = cues, y, size
        self._cache: dict[str, Patch] = {}

    def active_cue(self, t: float) -> str | None:
        return next((txt for s, e, txt in self.cues if s <= t < e), None)

    def draw(self, frame, ctx, t):
        txt = self.active_cue(t)
        if not txt:
            return frame
        if txt not in self._cache:
            b = ctx.brand
            self._cache[txt] = text_patch(b, txt, "title", self.size, "#FFFFFF", b.color("ref_keyword_green"),
                                          stroke=7, stroke_color="#000000", underline=True)
        return _place(frame, self._cache[txt], ctx, 540, self.y, 1.0, self.opacity)


# ============================================================== shared end card (both families)

def cloud_mask(w: int, h: int, bumps: list[tuple[float, float, float]], ss: int = 2) -> np.ndarray:
    """Union of circles (cx, cy, r as fractions of w) — procedural cloud like the reference end card."""
    m = np.zeros((h * ss, w * ss), np.uint8)
    for cx, cy, r in bumps:
        cv2.circle(m, (int(cx * w * ss), int(cy * w * ss)), int(r * w * ss), 255, -1, cv2.LINE_AA)
    return cv2.resize(m, (w, h), interpolation=cv2.INTER_AREA).astype(np.float32) / 255


_CLOUD_TR = [(0.30, 0.33, 0.20), (0.52, 0.22, 0.24), (0.76, 0.26, 0.22), (0.95, 0.20, 0.20), (0.62, 0.40, 0.16)]
_CLOUD_BL = [(0.06, 0.62, 0.20), (0.28, 0.48, 0.24), (0.52, 0.56, 0.20), (0.70, 0.66, 0.16), (0.22, 0.75, 0.22)]


class EndCard(Layer):
    """Light-grey card, green clouds top-right / bottom-left sliding in, 第十一屆 rule, lockup,
    serif 啟航北極星, spaced FIND YOUR NORTH STAR, dark CTA pill + paper plane.
    Ref: ChiliAng 1:04–1:09 and FB launch 0:51–0:59.5 (identical card in both)."""

    def __init__(self, edition: str, theme_zh: str, theme_en: str, cta_label: str, cta_url: str,
                 slogan: str = "", invite: str = "", name_en: str = "Dream Factory Startup Contest", **kw):
        super().__init__(**kw)
        self.name_en = name_en
        self.edition, self.theme_zh, self.theme_en = edition, theme_zh, theme_en
        self.cta_label, self.cta_url, self.slogan, self.invite = cta_label, cta_url, slogan, invite
        self._static: Patch | None = None
        self._clouds: tuple[Patch, Patch] | None = None

    def _build(self, ctx):
        # Layout measured on ChiliAng 1:07 (design px): edition rows 579–615, wordmark characters
        # 712–818 (≈980 px wide), 啟航北極星 1034–1140, FIND… 1163–1187, CTA pill 1272–1370 (#646568).
        b = ctx.brand
        W, H = 1080, 1920
        ink, green = b.color("ref_endcard_text"), b.color("ref_cloud_green")
        card = np.ones((H, W, 4), np.float32)
        card[..., :3] = resolve_color(b, b.color("ref_endcard_bg"))
        items: list[tuple[Patch, float, float]] = []
        ed = text_patch(b, self.edition, "heading", 40, ink, ink, tracking=0.35)
        items.append((ed, 540, 597))
        rule = np.zeros((3, 190, 4), np.float32)
        rule[..., :3], rule[..., 3] = resolve_color(b, ink), 1
        items += [(Patch(rule), 540 - ed.w / 2 - 130, 599), (Patch(rule), 540 + ed.w / 2 + 130, 599)]
        if "dfsc_name_zh" in b.logos:
            shape = dict(b.logo_shape("dfsc_name_zh"))
            shape["paths"] = [dict(p) for p in shape["paths"]]
            shape["paths"][-1]["fill"] = green          # last path = the 。 ring, green on the end card
            vw, vh = shape["viewbox"]
            nm = vector.render_shape(shape, int(980 * vh / vw), colors={"#1A1B1B": ink})
            items.append((nm, 540, 765))
        sub = text_patch(b, self.name_en, "heading", 36, b.color("ref_endcard_english_blue"),
                         b.color("ref_endcard_english_blue"), tracking=0.02)
        items.append((sub, 540, 882))
        th = text_patch(b, self.theme_zh, "serif_title", 122, ink, ink, tracking=0.04)
        items.append((th, 540, 1087))
        en = text_patch(b, self.theme_en.upper(), "body", 30, ink, ink, tracking=0.42)
        items.append((en, 540, 1176))
        y = 1260
        for line in (self.slogan, self.invite):          # only when supplied — never invented
            if line:
                lp = text_patch(b, line, "heading", 50, ink, green)
                items.append((lp, 540, y))
                y += 78
        lab = text_patch(b, self.cta_label, "heading", 40, "#D9D9D9", "#D9D9D9")
        url = text_patch(b, self.cta_url, "title", 42, green, green)
        sep = np.zeros((40, 2, 4), np.float32)
        sep[..., :3], sep[..., 3] = 0.85, 1
        pw, ph = max(lab.w + url.w + 200, 860), 98
        from ._util import rounded_rect_mask
        pill = np.zeros((ph, pw, 4), np.float32)
        pill[..., :3] = resolve_color(b, b.color("ref_endcard_pill"))
        pill[..., 3] = rounded_rect_mask(pw, ph, ph / 2)
        gap = (pw - lab.w - url.w) / 3
        paste(pill, lab.rgba, int(gap), (ph - lab.h) // 2)
        paste(pill, sep, int(gap * 1.5 + lab.w), (ph - 40) // 2)
        paste(pill, url.rgba, int(gap * 2 + lab.w), (ph - url.h) // 2)
        py = max(y + 60, 1321)
        items.append((Patch(pill), 540, py))
        self._plane = None
        if "paper_plane" in b.logos:       # flies in beside the pill at ~1:09 in the reference
            pl = vector.render_shape(b.logo_shape("paper_plane"), 72, colors={"#36B44A": b.color("ref_endcard_english_blue")})
            self._plane = (pl, 540 - pw / 2 - 20, py)
        for p, cx, cy in items:
            paste(card, p.rgba, int(cx - p.w / 2), int(cy - p.h / 2))
        self._static = Patch(card)
        clouds = []
        for bumps, (cw, chh) in ((_CLOUD_TR, (720, 470)), (_CLOUD_BL, (840, 700))):
            c = np.zeros((chh, cw, 4), np.float32)
            c[..., :3] = resolve_color(b, green)
            c[..., 3] = cloud_mask(cw, chh, bumps)
            clouds.append(Patch(c))
        self._clouds = tuple(clouds)

    def draw(self, frame, ctx, t):
        if self._static is None:
            self._build(ctx)
        fade = min(1.0, t / 0.25)
        frame = _place(frame, self._static, ctx, 540, 960, 1.0, fade * self.opacity)
        k = easing.progress(t, 0.1, 0.6, "out_cubic")
        tr, bl = self._clouds
        frame = _place(frame, tr, ctx, 380 + tr.w / 2 + (1 - k) * 600, 405 - tr.h / 2, 1.0, self.opacity)
        frame = _place(frame, bl, ctx, bl.w / 2 - 110 - (1 - k) * 600, 1350 + bl.h / 2, 1.0, self.opacity)
        if self._plane and t > 1.2:
            pl, px, py = self._plane
            kk = easing.progress(t, 1.2, 0.5, "out_cubic")
            frame = _place(frame, pl, ctx, px - (1 - kk) * 160, py + (1 - kk) * 60, 1.0, kk * self.opacity)
        return frame


# ============================================================== launch cinematic family

class LaunchBackground(Layer):
    """Deep-navy radial gradient, faint perspective-free grid, twinkling dots, vignette.
    Ref: FB launch 0:06–0:14 (centre #071C3C, edges #00050D)."""

    def __init__(self, grid: float = 96, seed: int = 7, **kw):
        super().__init__(**kw)
        self.grid, self.seed = grid, seed
        self._base: dict[tuple[int, int], np.ndarray] = {}

    def draw(self, frame, ctx, t):
        key = (ctx.width, ctx.height)
        if key not in self._base:
            b = ctx.brand
            h, w = frame.shape[:2]
            yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
            r = np.sqrt(((xx - w * 0.55) / w) ** 2 + ((yy - h * 0.42) / h) ** 2) / 0.75
            c0 = np.array(resolve_color(b, b.color("ref_launch_navy")), np.float32)
            c1 = np.array(resolve_color(b, b.color("ref_launch_edge")), np.float32)
            base = c0 + (c1 - c0) * np.clip(r, 0, 1)[..., None]
            step = max(ctx.px(self.grid), 8)
            gl = np.zeros((h, w), np.float32)
            gl[::step, :] = 1
            gl[:, ::step] = 1
            base = base + gl[..., None] * np.array([0.05, 0.09, 0.14], np.float32) * (1 - np.clip(r, 0, 1))[..., None]
            self._base[key] = base.astype(np.float32)
            rng = np.random.default_rng(self.seed)
            self._dots = np.c_[rng.uniform(0, w, 140), rng.uniform(0, h, 140), rng.uniform(0, 6.28, 140)]
        frame[:] = self._base[key]
        for x, y, ph in self._dots:
            a = 0.25 + 0.25 * math.sin(t * 1.7 + ph)
            xi, yi = int(x), int(y)
            frame[yi:yi + 2, xi:xi + 2] = frame[yi:yi + 2, xi:xi + 2] * (1 - a) + a
        return frame


class LaunchStar(_CachedLayer):
    """Brand tri-colour north star with a soft blue-white glow, gently breathing.
    Ref: FB launch 0:02–0:05 (star + stem, top-right) and 0:15–0:17 (centred)."""

    def __init__(self, x: float = 760, y: float = 330, height: float = 360, stem: bool = True, **kw):
        super().__init__(**kw)
        self.x, self.y, self.height, self.stem = x, y, height, stem

    def art(self, ctx):
        b = ctx.brand
        key = next((k for k in (("north_star_tricolor",) if self.stem else ("north_star_tricolor_nostem", "north_star_tricolor"))
                    if k in b.logos), None)
        shape = b.logo_shape(key) if key else vector.star_shape()
        st = vector.render_shape(shape, int(self.height))
        pad = int(self.height * 0.45)
        H, W = st.h + 2 * pad, st.w + 2 * pad
        glow = np.zeros((H, W, 4), np.float32)
        glow[pad:pad + st.h, pad:pad + st.w, 3] = st.rgba[..., 3]
        glow[..., :3] = (0.70, 0.85, 1.0)
        glow = canvas.blur_rgba(glow, self.height * 0.07)
        glow[..., 3] *= 0.8
        art = glow
        paste(art, st.rgba, pad, pad)
        # bright core + thin glints at the star's centre (film 0:15–0:17)
        cy, cx = pad + st.h * (0.5 if not self.stem else 0.36), W / 2
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        r = np.hypot(xx - cx, yy - cy) / self.height
        core = np.exp(-(r / 0.05) ** 2) + 0.35 * np.exp(-(r / 0.14) ** 2)
        glint = (np.exp(-((yy - cy) / (self.height * 0.006)) ** 2) * np.exp(-np.abs(xx - cx) / (self.height * 0.30))
                 + np.exp(-((xx - cx) / (self.height * 0.006)) ** 2) * np.exp(-np.abs(yy - cy) / (self.height * 0.22)))
        flare = np.clip(core + 0.8 * glint, 0, 1)[..., None]
        flare_rgba = np.concatenate([np.ones((H, W, 3), np.float32) * np.array([0.92, 0.97, 1.0], np.float32), flare], -1)
        paste(art, flare_rgba, 0, 0)
        return Patch(art)

    def draw(self, frame, ctx, t):
        a = min(1.0, t / 0.6)
        s = 1.0 + 0.02 * math.sin(t * 2.2)
        return _place(frame, self._get(ctx), ctx, self.x, self.y, s, a * self.opacity)


class LaunchSerifText(_CachedLayer):
    """White heavy-serif Traditional text that resolves from a blur (the film's soft cut-in), with an
    optional faded 'ghost' title kept in the corner afterwards. Ref: FB launch 0:09 「重來」, 0:04 subtitle."""

    def __init__(self, lines: list[str], x: float = 120, y: float = 760, size: int = 150,
                 role: str = "serif_title", align: str = "left", **kw):
        super().__init__(**kw)
        self.lines, self.x, self.y, self.size, self.role, self.align = lines, x, y, size, role, align

    def art(self, ctx):
        b = ctx.brand
        pats = [text_patch(b, ln, self.role, self.size, "#FFFFFF", b.color("ref_keyword_green"), shadow=4)
                for ln in self.lines]
        w = max(p.w for p in pats)
        gap = int(self.size * 0.25)
        h = sum(p.h for p in pats) + gap * (len(pats) - 1)
        art = np.zeros((h, w, 4), np.float32)
        y = 0
        for p in pats:
            x = 0 if self.align == "left" else (w - p.w) // 2
            art[y:y + p.h, x:x + p.w] = np.maximum(art[y:y + p.h, x:x + p.w], p.rgba)
            y += p.h + gap
        return Patch(art)

    def draw(self, frame, ctx, t):
        art = self._get(ctx)
        k = easing.progress(t, 0, 0.7, "out_cubic")
        p = Patch(canvas.blur_rgba(art.rgba, (1 - k) * 18) if k < 0.98 else art.rgba)
        cx = self.x + art.w / 2 if self.align == "left" else self.x
        return _place(frame, p, ctx, cx, self.y + art.h / 2, 1.0, k * self.opacity)


class LaunchAlumniOrbit(Layer):
    """Circular portraits with green rings arranged around the star, name under each.
    Placeholder portraits are generated (no real faces). Ref: FB launch 0:20–0:26."""

    def __init__(self, names: list[str], cx: float = 540, cy: float = 900, radius: float = 330,
                 portrait: float = 190, roles: list[str] | None = None, **kw):
        super().__init__(**kw)
        self.names, self.cx, self.cy, self.radius, self.portrait = names, cx, cy, radius, portrait
        self.roles = roles or [""] * len(names)
        self._tiles: list[Patch] | None = None

    def _tile(self, ctx, i: int, name: str) -> Patch:
        b = ctx.brand
        d = int(self.portrait)
        ring = max(d // 22, 4)
        tile = np.zeros((d, d, 4), np.float32)
        yy, xx = np.mgrid[0:d, 0:d].astype(np.float32)
        r = np.hypot(xx - d / 2, yy - d / 2)
        hue = (i * 0.17) % 1
        base = np.array([0.35 + 0.3 * hue, 0.45, 0.6 - 0.3 * hue], np.float32)
        face = base * (0.7 + 0.3 * (1 - yy / d))[..., None]
        disk = np.clip(d / 2 - ring - r, 0, 1)
        tile[:d, :, :3] = face
        tile[:d, :, 3] = disk
        ring_m = np.clip(1 - np.abs(r - (d / 2 - ring / 2)) / (ring / 2), 0, 1)
        green = np.array(resolve_color(b, b.color("ref_keyword_green")), np.float32)
        tile[:d, :, :3] = tile[:d, :, :3] * (1 - ring_m[..., None]) + green * ring_m[..., None]
        tile[:d, :, 3] = np.maximum(tile[:d, :, 3], ring_m)
        initials = text_patch(b, name.split()[-1][:1].upper(), "title", int(d * 0.38), "#FFFFFF", "#FFFFFF")
        paste(tile, initials.rgba, (d - initials.w) // 2, (d - initials.h) // 2)
        nm = text_patch(b, name, "heading", 30, "#FFFFFF", "#FFFFFF")
        role = self.roles[i] if i < len(self.roles) else ""
        rl = text_patch(b, role, "body", 22, b.color("ref_keyword_green"), b.color("ref_keyword_green")) if role else None
        tw = max(d, nm.w, rl.w if rl else 0)
        wide = np.zeros((d + 110, tw, 4), np.float32)
        paste(wide, tile[:d], (tw - d) // 2, 0)
        paste(wide, nm.rgba, (tw - nm.w) // 2, d + 6)
        if rl:
            paste(wide, rl.rgba, (tw - rl.w) // 2, d + 6 + nm.h - 4)
        return Patch(wide)
        return Patch(tile)

    def draw(self, frame, ctx, t):
        if self._tiles is None:
            self._tiles = [self._tile(ctx, i, n) for i, n in enumerate(self.names)]
        n = len(self._tiles)
        line_col = tuple(int(c * 255) for c in (0.55, 0.75, 1.0))
        for i in range(n):          # thin constellation lines from the star to each portrait (film 0:22)
            k = easing.progress(t, 0.12 * i, 0.5, "out_cubic")
            ang = -math.pi / 2 + 2 * math.pi * i / max(n, 1)
            x1, y1 = ctx.px(self.cx), ctx.px(self.cy)
            x2 = ctx.px(self.cx + self.radius * k * math.cos(ang))
            y2 = ctx.px(self.cy + self.radius * k * math.sin(ang))
            ov = frame.copy()
            cv2.line(ov, (x1, y1), (x2, y2), tuple(c / 255 for c in line_col), max(ctx.px(2), 1), cv2.LINE_AA)
            frame[:] = frame * 0.6 + ov * 0.4
        for i, tile in enumerate(self._tiles):
            k = easing.progress(t, 0.12 * i, 0.5, "out_back")
            ang = -math.pi / 2 + 2 * math.pi * i / max(n, 1) + (1 - k) * 0.4
            x = self.cx + self.radius * math.cos(ang)
            y = self.cy + self.radius * math.sin(ang)
            frame = _place(frame, tile, ctx, x, y, 0.6 + 0.4 * k, min(1, k * 1.5) * self.opacity)
        return frame


class LaunchStats(_CachedLayer):
    """Big white numbers with green '+', small label and green underline. Ref: FB launch 0:45–0:48."""

    def __init__(self, items: list[tuple[str, str]], y: float = 900, size: int = 120, footer: str = "", **kw):
        super().__init__(**kw)
        self.items, self.y, self.size, self.footer = items, y, size, footer

    def art(self, ctx):
        b = ctx.brand
        green = b.color("ref_keyword_green")
        cols = []
        for value, label in self.items:
            v = text_patch(b, value, "title", self.size, "#FFFFFF", green, shadow=3)
            lb = text_patch(b, label, "heading", 38, "#E8F2FF", "#E8F2FF")
            w = max(v.w, lb.w)
            uw = int(w * 1.15)
            col = np.zeros((v.h + lb.h + 40, uw, 4), np.float32)
            paste(col, v.rgba, (uw - v.w) // 2, 0)
            paste(col, lb.rgba, (uw - lb.w) // 2, v.h + 2)
            col[v.h + lb.h + 22:v.h + lb.h + 26, :, :3] = resolve_color(b, green)
            col[v.h + lb.h + 22:v.h + lb.h + 26, :, 3] = 1
            cols.append(col)
        gap = 50
        w = sum(c.shape[1] for c in cols) + gap * (len(cols) - 1)
        h = max(c.shape[0] for c in cols)
        ft = text_patch(b, self.footer, "serif_body", 50, "#FFFFFF", green, shadow=2) if self.footer else None
        W = max(w, (ft.w + 400) if ft else 0)
        art = np.zeros((h + (ft.h + 120 if ft else 0), W, 4), np.float32)
        x = (W - w) // 2
        for c in cols:
            paste(art, c, x, 0)
            x += c.shape[1] + gap
        if ft:
            fy = h + 120
            rule = resolve_color(b, b.color("ref_launch_rule_blue"))
            art[fy + ft.h // 2:fy + ft.h // 2 + 2, :, :3] = rule
            art[fy + ft.h // 2:fy + ft.h // 2 + 2, :, 3] = 0.9
            art[fy:fy + ft.h, (W - ft.w) // 2 - 20:(W + ft.w) // 2 + 20, 3] = 0   # gap behind the words
            paste(art, ft.rgba, (W - ft.w) // 2, fy)
        if art.shape[1] > 1000:                      # fit the 9:16 frame
            s = 1000 / art.shape[1]
            art = cv2.resize(art, (1000, int(art.shape[0] * s)), interpolation=cv2.INTER_AREA)
        return Patch(art)

    def draw(self, frame, ctx, t):
        k = easing.progress(t, 0, 0.6, "out_cubic")
        return _place(frame, self._get(ctx), ctx, 540, self.y + (1 - k) * 40, 1.0, k * self.opacity)
