"""Graphic elements of the Dream Factory interview style (measured from the reference).

All elements are rendered with PIL into RGBA numpy arrays (premultiplied later at
composite time). Sizes are for a 1080x1920 canvas.
"""
import math
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT_DIR = "/usr/share/fonts/opentype/noto/"
EMOJI_FONT = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"
TC = 3  # Traditional Chinese face inside the Noto CJK collections

# ---- palette (sampled from the reference frames) ----
WHITE = (249, 250, 252)
KW_GREEN = (104, 212, 104)        # subtitle keyword
UL_GREEN = (67, 172, 71)          # subtitle keyword underline
TITLE_GREEN = (106, 217, 105)     # green text in navy boxes
NAVY_TOP = (18, 38, 72)
NAVY_BOT = (15, 26, 49)
NAVY_EDGE = (117, 119, 127)
GREEN_L = (84, 200, 84)           # green box, left
GREEN_R = (58, 137, 58)           # green box, right
TAG_BG = (239, 241, 236)
TAG_TEXT = (24, 24, 24)
TAG_GREY = (150, 150, 150)
OUTLINE = (12, 14, 20)


@lru_cache(None)
def font(kind, size):
    path = {"sans_bold": "NotoSansCJK-Bold.ttc", "sans_black": "NotoSansCJK-Black.ttc",
            "serif_black": "NotoSerifCJK-Black.ttc"}[kind]
    return ImageFont.truetype(FONT_DIR + path, size, index=TC)


def _np(im):
    return np.asarray(im, dtype=np.float32) / 255.0


# --------------------------------------------------------------------------- text
def text_width(txt, fnt):
    return fnt.getlength(txt)


def runs_layout(runs, fnt, tracking=0):
    """runs: [(text, color)] -> list of (char, color, x) and total width."""
    x, out = 0.0, []
    for txt, col in runs:
        for ch in txt:
            out.append((ch, col, x))
            x += fnt.getlength(ch) + tracking
    return out, x - tracking


# --------------------------------------------------------------------------- subtitle
class SubtitleLine:
    """One subtitle line, laid out centred for the full phrase; characters are
    revealed in place as they are spoken (reference behaviour)."""
    SIZE = 64
    CY = 1300

    def __init__(self, units, kw_mask, width=1080):
        f = font("sans_bold", self.SIZE)
        self.units = units
        xs, x = [], 0.0
        for u in units:
            xs.append(x)
            x += f.getlength(u)
        total = x
        pad = 24
        H = self.SIZE + 2 * pad + 20
        W = int(total + 2 * pad)
        im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        base_y = pad
        # keyword underline bars (under the glyphs, drawn first so text overlaps)
        bars = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        bd = ImageDraw.Draw(bars)
        i = 0
        while i < len(units):
            if kw_mask[i]:
                j = i
                while j < len(units) and kw_mask[j]:
                    j += 1
                x0 = pad + xs[i]
                x1 = pad + (xs[j] if j < len(units) else total)
                y0 = base_y + self.SIZE + 2
                bd.rectangle([x0 - 2, y0 - 2, x1 + 2, y0 + 9], fill=OUTLINE + (230,))
                bd.rectangle([x0, y0, x1, y0 + 7], fill=UL_GREEN + (255,))
                i = j
            else:
                i += 1
        txt = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        td = ImageDraw.Draw(txt)
        for k, u in enumerate(units):
            col = KW_GREEN if kw_mask[k] else WHITE
            td.text((pad + xs[k], base_y + int(self.SIZE * 0.88)), u, font=f, fill=col + (255,),
                    stroke_width=3, stroke_fill=OUTLINE + (235,), anchor="ls")
        # soft drop shadow
        sh_a = txt.split()[3].filter(ImageFilter.GaussianBlur(4))
        shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        shadow.putalpha(sh_a.point(lambda v: int(v * 0.55)))
        im.alpha_composite(shadow, (0, 4))
        im.alpha_composite(bars)
        im.alpha_composite(txt)
        self.img = _np(im)
        self.x = int(round(width / 2 - W / 2))
        self.y = int(round(self.CY - H / 2))
        # column ranges per unit (for in-place reveal)
        self.col = np.zeros(W, dtype=np.int32)
        bounds = [pad + xx for xx in xs] + [pad + total]
        for k in range(len(units)):
            a = 0 if k == 0 else int((bounds[k]))
            self.col[a:] = k

    def frame(self, alphas):
        """alphas: per-unit opacity -> RGBA array"""
        w = np.asarray(alphas, dtype=np.float32)[self.col]
        out = self.img.copy()
        out[..., 3] *= w[None, :]
        return out


# --------------------------------------------------------------------------- boxes
def _gradient(w, h, c0, c1, horizontal=False):
    t = np.linspace(0, 1, w if horizontal else h, dtype=np.float32)
    g = (np.array(c0)[None, :] * (1 - t[:, None]) + np.array(c1)[None, :] * t[:, None])
    if horizontal:
        return np.repeat(g[None, :, :], h, 0)
    return np.repeat(g[:, None, :], w, 1)


def box_base(w, h, style):
    """Box background as RGBA float array."""
    if style == "navy":
        rgb = _gradient(w, h, NAVY_TOP, NAVY_BOT)
        # faint horizontal stripes (as in the reference)
        y = np.arange(h)[:, None]
        rgb = rgb * (1 + 0.06 * (np.sin(y / h * math.pi * 7) > 0.6))[..., None]
        edge = NAVY_EDGE
    elif style == "green":
        rgb = _gradient(w, h, GREEN_L, GREEN_R, horizontal=True)
        y = np.arange(h)[:, None] / h
        rgb = rgb * (1.06 - 0.10 * y)[..., None]
        edge = (170, 225, 170)
    else:  # tag
        rgb = np.ones((h, w, 3), np.float32) * np.array(TAG_BG)
        edge = None
    a = np.ones((h, w, 1), np.float32)
    img = np.concatenate([np.clip(rgb, 0, 255) / 255.0, a], 2)
    if edge is not None:
        e = np.array(edge, np.float32) / 255.0
        img[:2, :, :3] = e; img[-2:, :, :3] = e; img[:, :2, :3] = e; img[:, -2:, :3] = e
    if style == "tag":
        img[..., 3] = 0.94
    return img


class TextBox:
    """Navy / green / tag box with a line of text made of coloured runs."""

    def __init__(self, runs, style="navy", size=110, pad_x=None, pad_y=None, kind="sans_black"):
        f = font(kind, size)
        self.style, self.size = style, size
        chars, tw = runs_layout(runs, f)
        pad_x = int(size * 0.56) if pad_x is None else pad_x
        pad_y = int(size * 0.50) if pad_y is None else pad_y
        ref = f.getbbox("國", anchor="ls")
        txt = "".join(t for t, _ in runs)
        bb = f.getbbox(txt, anchor="ls")
        top, bot = min(ref[1], bb[1]), max(ref[3], bb[3])
        self.w, self.h = int(tw + 2 * pad_x), int((bot - top) + 2 * pad_y)
        base = pad_y - top
        self.bg = box_base(self.w, self.h, style)
        # each char rendered on its own strip (full box height) so it can fade in on its own
        self.glyphs = []
        m = int(size * 0.3)
        for ch, col, x in chars:
            if not ch.strip():
                continue
            g = Image.new("RGBA", (int(f.getlength(ch)) + 2 * m, self.h), (0, 0, 0, 0))
            ImageDraw.Draw(g).text((m, base), ch, font=f, fill=tuple(col) + (255,), anchor="ls")
            self.glyphs.append((_np(g), int(pad_x + x - m), 0))

    def render(self, t, dur):
        """Animated RGBA canvas (same size as box) at local time t."""
        fps = 24
        enter = 5 / fps
        out_t = 5 / fps
        # horizontal grow from a thin bar
        if t < enter:
            p = 1 - (1 - t / enter) ** 3
            sx = 0.04 + 0.96 * p
        elif t > dur - out_t:
            p = (dur - t) / out_t
            sx = max(0.02, p ** 2)
        else:
            sx = 1.0
        canvas = self.bg.copy()
        # glyph reveal: staggered fade, starting when the box is mostly open
        t0, stag = enter * 0.5, 1.0 / fps
        for i, (g, gx, gy) in enumerate(self.glyphs):
            a = np.clip((t - t0 - i * stag) / (2 / fps), 0, 1)
            if t > dur - out_t:
                a *= np.clip((dur - t) / (out_t * 0.6), 0, 1)
            if a <= 0:
                continue
            _blend(canvas, g, gx, gy, a)
        # diagonal light sweep after the text is in
        ts = t - (t0 + len(self.glyphs) * stag + 2 / fps)
        if 0 < ts < 0.55 and self.style != "tag":
            x = -0.2 * self.w + ts / 0.55 * 1.4 * self.w
            yy, xx = np.mgrid[0:self.h, 0:self.w]
            band = np.abs((xx - x) - (self.h - yy) * 0.35)
            m = np.clip(1 - band / (self.h * 0.12), 0, 1) * 0.28
            canvas[..., :3] = canvas[..., :3] * (1 - m[..., None]) + m[..., None]
        if sx < 0.999:
            nw = max(2, int(self.w * sx))
            small = np.asarray(Image.fromarray((canvas * 255).astype(np.uint8), "RGBA").resize((nw, self.h)),
                               np.float32) / 255
            canvas = np.zeros_like(canvas)
            x0 = (self.w - nw) // 2
            canvas[:, x0:x0 + nw] = small
            if t < enter * 0.5:            # the reference shows a translucent grey frame at the very start
                canvas[..., 3] *= 0.75
        return canvas


def _blend(dst, src, x, y, a=1.0):
    """alpha-composite src (RGBA float) onto dst (RGBA float) in place."""
    x, y = int(round(x)), int(round(y))
    h, w = src.shape[:2]
    H, W = dst.shape[:2]
    x0, y0, x1, y1 = max(0, x), max(0, y), min(W, x + w), min(H, y + h)
    if x0 >= x1 or y0 >= y1:
        return
    s = src[y0 - y:y1 - y, x0 - x:x1 - x]
    d = dst[y0:y1, x0:x1]
    sa = s[..., 3:4] * a
    da = d[..., 3:4]
    oa = sa + da * (1 - sa)
    rgb = (s[..., :3] * sa + d[..., :3] * da * (1 - sa)) / np.maximum(oa, 1e-6)
    d[..., :3] = rgb
    d[..., 3:4] = oa


# --------------------------------------------------------------------------- serif emphasis
class SerifWord:
    """Big serif word, white (or green) fill, dark outline, shadow; characters zoom in."""

    def __init__(self, text, size=150, fill=WHITE, stroke=8):
        f = font("serif_black", size)
        self.chars = []
        x = 0
        for ch in text:
            cw = f.getlength(ch)
            S = int(size * 1.6)
            g = Image.new("RGBA", (S, S), (0, 0, 0, 0))
            d = ImageDraw.Draw(g)
            o = int(size * 0.3)
            d.text((o, o + int(size * 0.9)), ch, font=f, fill=tuple(fill) + (255,), stroke_width=stroke,
                   stroke_fill=OUTLINE + (255,), anchor="ls")
            sh = g.split()[3].filter(ImageFilter.GaussianBlur(6)).point(lambda v: int(v * 0.6))
            gs = Image.new("RGBA", (S, S), (0, 0, 0, 0))
            gs.putalpha(sh)
            base = Image.new("RGBA", (S, S), (0, 0, 0, 0))
            base.alpha_composite(gs, (4, 8))
            base.alpha_composite(g)
            self.chars.append((base, x - o))
            x += cw
        self.w = int(x)
        self.size = size

    def render(self, t, dur, canvas, cx, cy):
        fps = 24
        x_left = int(cx - self.w / 2)
        for i, (g, dx) in enumerate(self.chars):
            lt = t - i * 2 / fps
            if lt <= 0:
                continue
            p = min(1.0, lt / (5 / fps))
            ease = 1 - (1 - p) ** 3
            sc = 1.7 - 0.7 * ease
            a = min(1.0, p * 1.4)
            if t > dur - 4 / fps:
                a *= max(0.0, (dur - t) / (4 / fps))
            im = g
            if p < 1:
                im = g.filter(ImageFilter.GaussianBlur((1 - p) * 10))
            S = int(g.width * sc)
            im = im.resize((S, S), Image.BILINEAR)
            arr = _np(im)
            gx = x_left + dx + int(g.width / 2 - S / 2)
            gy = int(cy - self.size * 0.5 - self.size * 0.3 + g.height / 2 - S / 2)
            _blend(canvas, arr, gx, gy, a)


# --------------------------------------------------------------------------- emoji sticker
@lru_cache(None)
def emoji_sticker(ch, size=150):
    f = ImageFont.truetype(EMOJI_FONT, 109)
    g = Image.new("RGBA", (160, 160), (0, 0, 0, 0))
    ImageDraw.Draw(g).text((80, 80), ch, font=f, embedded_color=True, anchor="mm")
    bb = g.getbbox()
    g = g.crop(bb)
    s = size / max(g.size)
    g = g.resize((max(1, int(g.width * s)), max(1, int(g.height * s))), Image.LANCZOS)
    pad = 14
    W, H = g.width + 2 * pad, g.height + 2 * pad
    a = Image.new("L", (W, H), 0)
    a.paste(g.split()[3], (pad, pad))
    # white sticker outline + soft shadow
    outline = a.filter(ImageFilter.MaxFilter(13)).filter(ImageFilter.GaussianBlur(1.2))
    shadow = outline.filter(ImageFilter.GaussianBlur(5)).point(lambda v: int(v * 0.35))
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0)); sh.putalpha(shadow)
    out.alpha_composite(sh, (0, 3))
    wl = Image.new("RGBA", (W, H), (255, 255, 255, 0)); wl.putalpha(outline)
    out.alpha_composite(wl)
    gg = Image.new("RGBA", (W, H), (0, 0, 0, 0)); gg.paste(g, (pad, pad))
    out.alpha_composite(gg)
    return out


def render_sticker(canvas, ch, t, dur, cx, cy, size=150, phase=0.0):
    """Pop-in with overshoot, gentle wobble, pop-out."""
    if t < 0:
        return
    fps = 24
    p = min(1.0, t / (6 / fps))
    sc = (1 - (1 - p) ** 3) * (1 + 0.18 * math.sin(p * math.pi))
    if t > dur - 4 / fps:
        sc *= max(0.0, (dur - t) / (4 / fps))
    if sc <= 0.02:
        return
    rot = 5 * math.sin(2 * math.pi * 0.6 * t + phase)
    im = emoji_sticker(ch, size)
    im = im.resize((max(1, int(im.width * sc)), max(1, int(im.height * sc))), Image.BILINEAR)
    im = im.rotate(rot, resample=Image.BICUBIC, expand=True)
    _blend(canvas, _np(im), int(cx - im.width / 2), int(cy - im.height / 2))


# --------------------------------------------------------------------------- sparkles
@lru_cache(None)
def star_sprite(size, gold=False):
    S = size * 2 + 1
    yy, xx = np.mgrid[-size:size + 1, -size:size + 1].astype(np.float32)
    r = np.hypot(xx, yy) + 1e-6
    rays = np.exp(-np.abs(xx) / (size * 0.05)) * np.exp(-np.abs(yy) / (size * 0.55)) + \
        np.exp(-np.abs(yy) / (size * 0.05)) * np.exp(-np.abs(xx) / (size * 0.55))
    glow = np.exp(-r / (size * 0.12))
    a = np.clip(rays * 0.9 + glow, 0, 1)
    col = np.array([1.0, 0.86, 0.55] if gold else [1.0, 0.97, 0.9], np.float32)
    img = np.zeros((S, S, 4), np.float32)
    img[..., :3] = col
    img[..., 3] = a
    return img


def render_star(canvas, t, dur, cx, cy, size=60, gold=False):
    """Glint: grows, rotates slightly, shrinks."""
    if t < 0 or t > dur:
        return
    p = t / dur
    s = math.sin(p * math.pi)
    if s < 0.05:
        return
    spr = star_sprite(size, gold)
    sz = max(3, int(spr.shape[0] * s))
    im = Image.fromarray((spr * 255).astype(np.uint8), "RGBA").resize((sz, sz), Image.BILINEAR)
    im = im.rotate(20 * p, resample=Image.BICUBIC)
    _blend(canvas, _np(im), int(cx - sz / 2), int(cy - sz / 2))
