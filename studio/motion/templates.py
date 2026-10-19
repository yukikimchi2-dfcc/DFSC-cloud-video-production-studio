"""Reusable motion-graphics templates.

A template = templates/<id>/template.yaml (metadata, parameters, review status, test record pointer)
           + a builder function registered here with @register("<id>").

    layers = build_template("stat_counter", {"value": 1200, "label": "位創業者"}, brand)
    timeline.add(*layers)

Builders are brand-agnostic: colours/fonts/logos come from the BrandKit passed in, so the same
template renders on-brand for any project.
"""
from __future__ import annotations

import datetime as dt
import json
import time
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image

from studio.brand import BrandKit, load_brand
from studio.config import TEMPLATES_DIR, load_yaml
from studio.core import canvas, easing, vector
from studio.core.canvas import Patch
from studio.core.timeline import FuncLayer, Layer, SolidLayer, Timeline

from . import cards, particles
from ._util import readable_on, resolve_hex
from .camera import CameraShake, SlowPushIn
from .typography import TextLayer, WordHighlightLayer

Builder = Callable[[dict, BrandKit], list[Layer]]
_BUILDERS: dict[str, Builder] = {}


def register(template_id: str):
    def deco(fn: Builder) -> Builder:
        _BUILDERS[template_id] = fn
        return fn
    return deco


class TemplateError(ValueError):
    pass


def list_templates() -> list[dict]:
    """Metadata of every template on disk (sorted by id)."""
    out = []
    for f in sorted(TEMPLATES_DIR.glob("*/template.yaml")):
        meta = load_yaml(f)
        meta["_dir"] = str(f.parent)
        meta["has_builder"] = meta.get("id") in _BUILDERS
        out.append(meta)
    return out


def get_template(template_id: str) -> dict:
    f = TEMPLATES_DIR / template_id / "template.yaml"
    if not f.exists():
        raise TemplateError(f"Unknown template '{template_id}'. Available: {[t['id'] for t in list_templates()]}")
    meta = load_yaml(f)
    meta["_dir"] = str(f.parent)
    return meta


def _auto(brand: BrandKit, value, background, preferred="text") -> str:
    """'auto' colour -> readable text colour on `background`."""
    return readable_on(brand, background, preferred) if value == "auto" else value


def resolve_params(meta: dict, params: dict | None) -> dict:
    """Defaults from template.yaml merged with caller params; unknown params are rejected."""
    spec = {p["name"]: p for p in meta.get("parameters", [])}
    unknown = set(params or {}) - set(spec)
    if unknown:
        raise TemplateError(f"Template '{meta['id']}' has no parameter(s) {sorted(unknown)}. Known: {sorted(spec)}")
    out = {name: p.get("default") for name, p in spec.items()}
    out.update(params or {})
    return out


def build_template(template_id: str, params: dict | None = None, brand: BrandKit | None = None,
                   start: float = 0.0) -> list[Layer]:
    meta = get_template(template_id)
    if template_id not in _BUILDERS:
        raise TemplateError(f"Template '{template_id}' has no registered builder")
    p = resolve_params(meta, params)
    layers = _BUILDERS[template_id](p, brand or BrandKit.neutral())
    for layer in layers:
        layer.start += start
    return layers


def template_duration(template_id: str, params: dict | None = None) -> float:
    meta = get_template(template_id)
    return float(resolve_params(meta, params).get("duration") or meta.get("duration", 4.0))


# ---------------------------------------------------------------- preview rendering

def synthetic_background(seed: int = 0) -> Layer:
    """Moving gradient stand-in for footage (clearly synthetic) used in template previews/tests."""
    rng = np.random.default_rng(seed)
    c = rng.uniform(0.15, 0.45, (2, 3)).astype(np.float32)

    def fn(frame, ctx, t):
        h, w = frame.shape[:2]
        ys = np.linspace(0, 1, h, dtype=np.float32)[:, None, None]
        xs = np.linspace(0, 1, w, dtype=np.float32)[None, :, None]
        wave = 0.5 + 0.5 * np.sin(2 * np.pi * (xs * 0.8 + ys * 0.6 + t * 0.15))
        frame[:] = c[0] * (1 - wave) + c[1] * wave
        return frame
    return FuncLayer(fn, z=-100, name="synthetic_background")


def preview_timeline(template_id: str, brand: BrandKit, params: dict | None = None,
                     width: int = 540, height: int = 960) -> Timeline:
    meta = get_template(template_id)
    params = {**meta.get("preview", {}).get("params", {}), **(params or {})}
    dur = template_duration(template_id, params)
    bg = meta.get("preview", {}).get("background", "synthetic")
    tl = Timeline(1080, 1920, fps=meta.get("preview", {}).get("fps", 20), duration=dur, brand=brand,
                  background=resolve_hex(brand, bg) if bg != "synthetic" else "#000000")
    if bg == "synthetic":
        tl.add(synthetic_background())
    elif bg == "synthetic_room":
        tl.add(dfsc_room_background())
    tl.add(*build_template(template_id, params, brand))
    return tl


def render_template_preview(template_id: str, out_dir: str | Path | None = None, project_id: str | None = None,
                            width: int = 540, height: int = 960, gif_width: int = 216, gif_fps: int = 8,
                            params: dict | None = None) -> dict:
    """Write preview.png (frame at preview.time), preview.gif (≤ ~1.5MB) and test_record.json."""
    meta = get_template(template_id)
    out = Path(out_dir or meta["_dir"])
    out.mkdir(parents=True, exist_ok=True)
    pid = project_id or meta.get("preview", {}).get("project")
    brand = load_brand(pid)
    tl = preview_timeline(template_id, brand, params, width, height)
    t0 = time.time()
    ctx = tl.context(width, height)
    t_prev = float(meta.get("preview", {}).get("time", tl.duration * 0.6))
    still = canvas.to_uint8(tl.render_frame(t_prev, ctx))
    Image.fromarray(still).save(out / "preview.png", optimize=True)
    gh = int(round(gif_width * height / width)) // 2 * 2
    gctx = tl.context(gif_width, gh)
    frames = []
    n = int(tl.duration * gif_fps)
    for i in range(n):
        img = Image.fromarray(canvas.to_uint8(tl.render_frame(i / gif_fps, gctx)))
        frames.append(img.quantize(colors=64, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE))
    gif = out / "preview.gif"
    frames[0].save(gif, save_all=True, append_images=frames[1:], duration=int(1000 / gif_fps), loop=0, optimize=True)
    elapsed = time.time() - t0
    nonblank = float(still.std()) > 2.0
    record = {
        "template": template_id, "version": meta.get("version"), "tested_at": dt.datetime.now().isoformat(timespec="seconds"),
        "brand": brand.name, "frames_rendered": n + 1, "render_seconds": round(elapsed, 2),
        "preview_png": "preview.png", "preview_gif": "preview.gif", "gif_bytes": gif.stat().st_size,
        "checks": {"nonblank_frame": nonblank, "gif_under_1_5mb": gif.stat().st_size <= 1_500_000},
        "passed": nonblank,
    }
    (out / "test_record.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"png": str(out / "preview.png"), "gif": str(gif), "record": record}


# ---------------------------------------------------------------- generic templates

@register("title_card_impact")
def _title_card_impact(p: dict, brand: BrandKit) -> list[Layer]:
    d = p["duration"]
    p["text_color"] = _auto(brand, p["text_color"], p["color"])
    layers: list[Layer] = [
        cards.ImpactCard(p["text"], x=70, y=p["y"], w=870, h=p["height"], color=p["color"], text_color=p["text_color"],
                         size=p["size"], radius=p["radius"], duration=d, exit="scale", exit_duration=0.3, z=10),
        CameraShake(intensity=0.012, decay=7, start=0.12, duration=0.8, z=5),
    ]
    if p.get("subtitle"):
        layers.append(TextLayer(p["subtitle"], x=505, y=p["y"] + p["height"] + 40, size=52, role="body", color="#FFFFFF",
                                shadow={"blur": 8, "opacity": 0.5},
                                animation="fade", start=0.45, duration=d - 0.45, exit="fade", z=11))
    if p.get("sparkles"):
        layers.append(particles.StarSparkles(count=14, region=(80, p["y"] - 200, 1000, p["y"] + p["height"] + 200),
                                             color="#FFFFFF", start=0.2, duration=d - 0.2, z=12))
    return layers


@register("lower_third_basic")
def _lower_third(p: dict, brand: BrandKit) -> list[Layer]:
    d = p["duration"]
    x, y = 70, p["y"]
    p["text_color"] = _auto(brand, p["text_color"], p["color"])
    if readable_on(brand, p["color"], p["accent"], 1.5) != brand.color(p["accent"]).upper():
        p["accent"] = p["text_color"]
    bar = cards.SolidPanel(x=x, y=y, w=p["width"], h=170, color=p["color"], radius=14, enter="expand",
                           enter_duration=0.45, ease="out_expo", exit="slide_right", duration=d, safe_clamp=True,
                           content=[
                               TextLayer(p["name"], x=x + 40, y=y + 26, size=62, role="title", color=p["text_color"],
                                         align="left", animation="fly_in", stagger=0.03, safe_clamp=False),
                               TextLayer(p["title"], x=x + 42, y=y + 106, size=36, role="body", color=p["text_color"],
                                         align="left", animation="fade", start=0.25, safe_clamp=False),
                           ], clip_content=True, z=10)
    accent = cards.SolidPanel(x=x, y=y, w=14, h=170, color=p["accent"], radius=0, enter="slide_up",
                              enter_duration=0.3, exit="fade", duration=d, z=11, safe_clamp=True)
    return [bar, accent]


@register("stat_counter")
def _stat_counter(p: dict, brand: BrandKit) -> list[Layer]:
    p["text_color"] = _auto(brand, p["text_color"], p["color"])
    return [cards.StatCard(p["value"], label=p["label"], prefix=p["prefix"], suffix=p["suffix"],
                           decimals=p["decimals"], count_duration=p["count_duration"], x=75, y=p["y"], w=860, h=420,
                           color=p["color"], number_color=p["text_color"], label_color=p["text_color"],
                           panel_opacity=p["panel_opacity"], duration=p["duration"], enter="pop", z=10)]


@register("quote_card")
def _quote_card(p: dict, brand: BrandKit) -> list[Layer]:
    p["text_color"] = _auto(brand, p["text_color"], p["color"])
    p["accent"] = readable_on(brand, p["color"], p["accent"], 1.8)
    return [cards.QuoteCard(p["quote"], author=p["author"], x=75, y=p["y"], w=860, h=p["height"], color=p["color"],
                            text_color=p["text_color"], accent=p["accent"], duration=p["duration"],
                            shadow={"blur": 24, "opacity": 0.3}, z=10)]


@register("cta_card_end")
def _cta_end(p: dict, brand: BrandKit) -> list[Layer]:
    d = p["duration"]
    p["button_text_color"] = _auto(brand, p["button_text_color"], p["button_color"])
    return [
        TextLayer(p["headline"], x=505, y=620, size=96, role="title", color=p["text_color"], animation="slam", stagger=0.05,
                  duration=d, sweep={"start": 1.2}, z=10),
        cards.CTACard(p["button_text"], sub=p["sub"], x=170, y=980, w=670, h=150, color=p["button_color"],
                      text_color=p["button_text_color"], start=0.6, duration=d - 0.6, exit=None, z=11),
        particles.StarSparkles(count=18, region=(60, 400, 1020, 1400), color=p["text_color"], start=0.4,
                               duration=d - 0.4, z=12),
    ]


@register("brand_lockup_outro")
def _brand_outro(p: dict, brand: BrandKit) -> list[Layer]:
    d = p["duration"]
    p["text_color"] = _auto(brand, p["text_color"], p["panel_color"] or p["on_color"])
    layers: list[Layer] = [
        cards.BrandLockupCard(logo=p["logo"], logo_height=p["logo_height"], tagline=p["tagline"],
                              tagline_color=p["text_color"], x=75, y=720, w=860, h=480, color=p["panel_color"],
                              panel=bool(p["panel_color"]), duration=d, exit=None, z=10),
        particles.ParticleEmitter(origin=(505, 900), burst=50, rate=0, lifetime=1.6, gravity=120, speed=(200, 700),
                                  colors=[p["text_color"], "primary", "secondary"], start=0.35, duration=2.0, z=11),
    ]
    if p.get("vignette"):
        layers.append(particles.Vignette(strength=0.35, z=20))
    return layers


@register("subtitle_word_highlight")
def _subtitle_highlight(p: dict, brand: BrandKit) -> list[Layer]:
    words = p["words"]
    if isinstance(words, str):  # "創業|是|一場|冒險" -> evenly timed demo words
        parts = [w for w in words.split("|") if w]
        step = p["duration"] / max(len(parts), 1)
        words = [{"text": w, "start": i * step, "end": (i + 1) * step} for i, w in enumerate(parts)]
    return [WordHighlightLayer(words, x=505, max_width=820, y=p["y"], size=p["size"], color=p["text_color"], highlight_color=p["highlight_color"],
                               pill_color=p["pill_color"], stroke=p["stroke"], duration=p["duration"], z=30)]


# ---------------------------------------------------------------- DFSC 2027

class _NorthStarLayer(Layer):
    """DFSC tri-colour north star: star spins in to its final 45° X pose, then the stem extends down."""

    def __init__(self, logo="north_star_tricolor", cx=600, cy=560, star_size=520, spin_duration=1.0,
                 stem_start=1.0, stem_duration=0.6, colors=None, **kw):
        super().__init__(**kw)
        self.logo, self.cx, self.cy, self.star_size = logo, cx, cy, star_size
        self.spin_duration, self.stem_start, self.stem_duration, self.colors = spin_duration, stem_start, stem_duration, colors
        self._cache: dict = {}

    def _parts(self, ctx):
        key = (ctx.scale, id(ctx.brand))
        if key not in self._cache:
            shape = ctx.brand.logo_shape(self.logo) if self.logo in getattr(ctx.brand, "logos", {}) else None
            if shape is None:
                star = vector.star_shape(4, 1.0, 0.3)
                self._cache[key] = (vector.render_shape(star, ctx.px(self.star_size), self.colors), None, 0)
            else:
                vw, vh = shape["viewbox"]
                star_paths = shape["paths"][:3]
                stem_path = shape["paths"][3:]
                ys = [pt[1] for pth in star_paths for sp in pth["subpaths"] for pt in sp]
                star_h = max(ys) - min(ys)
                s = ctx.px(self.star_size) / star_h
                star_only = {"viewbox": [vw, star_h], "paths": star_paths}
                stem = {"viewbox": [vw, vh], "paths": stem_path}
                sp = vector.render_shape(star_only, ctx.px(self.star_size), self.colors)
                stp = vector.render_shape(stem, int(round(vh * s)), self.colors) if stem_path else None
                self._cache[key] = (sp, stp, star_h * s)
        return self._cache[key]

    def render(self, ctx, t):
        star, stem, star_h = self._parts(ctx)
        cx, cy = ctx.px(self.cx), ctx.px(self.cy)
        p = easing.progress(t, 0, self.spin_duration, "out_back")
        raw = easing.clamp01(t / max(self.spin_duration, 1e-6))
        group = Patch(np.zeros((ctx.height, ctx.width, 4), np.float32))
        from ._util import over
        if stem is not None:
            q = easing.progress(t, self.stem_start, self.stem_duration, "out_expo")
            if q > 0:
                sp = Patch(stem.rgba.copy(), cx - stem.w // 2, cy - int(star_h / 2))
                vis = int(star_h * 0.6 + (stem.h - star_h * 0.6) * q)
                sp.rgba[vis:, :, 3] = 0
                over(group, sp)
        if raw > 0:
            st = Patch(star.rgba, cx - star.w // 2, cy - star.h // 2)
            st = canvas.transform_patch(st, max(0.15 + 0.85 * p, 0.0), -270 * (1 - p))
            over(group, st, min(1.0, raw * 3))
        return group


@register("dfsc2027_north_star_open")
def _dfsc_open(p: dict, brand: BrandKit) -> list[Layer]:
    green, black, white = resolve_hex(brand, p["green"]), resolve_hex(brand, p["black"]), "#FFFFFF"
    line = resolve_hex(brand, p["guide_color"])
    layers: list[Layer] = [
        # --- scene 1: white panel, tri-colour north star, 啟航 北極星
        SolidLayer(white, duration=2.6, z=-50),
        particles.GuideRectLayer(rect=(640, 120, 100, 1500), color=line, thickness=2, start=0.0, draw_duration=0.9, z=-40, duration=2.6),
        particles.GuideRectLayer(rect=(260, 1330, 620, 160), color=line, thickness=2, start=0.25, draw_duration=0.8, z=-40, duration=2.6),
        _NorthStarLayer(cx=690, cy=620, star_size=520, start=0.15, duration=2.45, z=0),
        TextLayer("北極星", x=250, y=900, size=64, role="body", color=black, vertical=True, tracking=10,
                  animation="fade", stagger=0.12, start=1.3, duration=1.3, z=2),
        particles.StarSparkles(count=8, region=(420, 300, 960, 900), size_range=(14, 34), color="secondary",
                               start=1.2, duration=1.4, z=3),
        # --- scene 2: green panel, 2027 with star inside the 0, Find Your North Star
        particles.PanelWipeLayer(color=green, direction="left", wipe_duration=0.45, start=2.4, duration=2.3, z=10),
        particles.GuideRectLayer(rect=(170, 140, 100, 1300), color=white, thickness=2, start=2.7, draw_duration=0.8, z=11, duration=2.0, line_opacity=0.5),
        TextLayer("27", x=1000, y=230, size=470, role="numerals_thin", color=white, align="right", animation="fly_in",
                  stagger=0.1, start=2.75, duration=1.95, tracking=-10, safe_clamp=False, z=12),
        particles.EllipseRingLayer(center=(600, 900), radii=(230, 150), color=white, thickness=34, start=2.9,
                                   draw_duration=0.6, duration=1.8, z=12),
        _NorthStarLayer(logo="north_star_black", cx=600, cy=900, star_size=250, spin_duration=0.8, start=3.1, duration=1.6, z=13),
        TextLayer("2", x=150, y=1020, size=470, role="numerals_thin", color=white, align="left", animation="fly_in",
                  start=3.2, duration=1.5, safe_clamp=False, z=12),
        TextLayer(brand_copy(brand, "theme_en", "Find Your North Star"), x=760, y=1420, size=46, role="body",
                  color=white, align="left", rotation=90, animation="fade", stagger=0.02, start=3.5, duration=1.2, z=12),
        # --- scene 3: white, 第十一屆 vertical, DFSC lockup
        particles.PanelWipeLayer(color=white, direction="up", wipe_duration=0.45, start=4.6, duration=2.4, z=20),
        particles.GuideRectLayer(rect=(120, 1250, 860, 170), color=line, thickness=2, start=4.9, draw_duration=0.8, angle=-8, z=21, duration=2.1),
        TextLayer(brand_copy(brand, "edition", "第十一屆"), x=180, y=300, size=110, role="body", color=black,
                  vertical=True, tracking=150, animation="drop", stagger=0.14, start=4.95, duration=2.05, safe_clamp=False, z=22),
        cards.BrandLockupCard(logo="dfsc_lockup", logo_height=230, x=300, y=900, w=650, h=320, color=white,
                              panel=False, enter="scale", enter_duration=0.6, start=5.3, duration=1.7, exit=None, z=23),
    ]
    if p.get("show_qihang", True):
        layers.append(_WordmarkLayer("qihang_wordmark", x=120, y=330, height=430, start=0.9, duration=1.7, z=1))
    return layers


def brand_copy(brand: BrandKit, key: str, default: str) -> str:
    """Brand copy lines live under `copy:` in brand.yaml (optional)."""
    try:
        from studio.config import PROJECTS_DIR
        data = load_yaml(PROJECTS_DIR / brand.project_id / "brand" / "brand.yaml")
        return data.get("copy", {}).get(key, default)
    except Exception:
        return default


class _WordmarkLayer(Layer):
    """Brand logo shape revealed top-to-bottom with a soft edge (used for 啟航)."""

    def __init__(self, logo: str, x: float, y: float, height: float, reveal_duration: float = 0.7, **kw):
        super().__init__(**kw)
        self.logo, self.x, self.y, self.height, self.reveal_duration = logo, x, y, height, reveal_duration
        self._cache: dict = {}

    def render(self, ctx, t):
        key = (ctx.scale, id(ctx.brand))
        if key not in self._cache:
            if self.logo not in getattr(ctx.brand, "logos", {}):
                return None
            self._cache[key] = vector.render_shape(ctx.brand.logo_shape(self.logo), ctx.px(self.height))
        base = self._cache[key]
        p = easing.progress(t, 0, self.reveal_duration, "out_cubic")
        if p <= 0:
            return None
        rgba = base.rgba.copy()
        h = rgba.shape[0]
        edge = p * (h + 20) - 10
        ys = np.arange(h, dtype=np.float32)[:, None]
        rgba[..., 3] *= np.clip((edge - ys) / 10, 0, 1)
        return Patch(rgba, ctx.px(self.x), ctx.px(self.y))


# ---------------------------------------------------------------- DFSC reference-based families
# Rebuilt from the edited reference videos (user-authorised style baseline, 2026-10-19).
# Sources per template: templates/<id>/template.yaml `sources` + projects/dfsc-2027/references/TEMPLATE_SOURCES.md

from . import dfsc as _d  # noqa: E402


def _cues(lines: list[str], start: float, per_line: float) -> list[tuple[float, float, str]]:
    return [(start + i * per_line, start + (i + 1) * per_line, ln) for i, ln in enumerate(lines)]


def dfsc_room_background() -> Layer:
    """Synthetic stand-in for an interview room (warm wall, darker floor) — never real footage."""
    def fn(frame, ctx, t):
        h = frame.shape[0]
        y = np.linspace(0, 1, h, dtype=np.float32)[:, None, None]
        frame[:] = np.array([0.80, 0.74, 0.66], np.float32) * (1 - 0.28 * y) + np.float32(0.02) * y
        return frame
    return FuncLayer(fn, z=-100, name="synthetic_room")


@register("dfsc_interview_top_label")
def _dfsc_top_label(p: dict, brand: BrandKit) -> list[Layer]:
    return [_d.InterviewTopLabel(p["text"], sticker=p["sticker"] or None, duration=p["duration"], z=20)]


@register("dfsc_interview_big_title")
def _dfsc_big_title(p: dict, brand: BrandKit) -> list[Layer]:
    out = [_d.InterviewBigTitle(p["title"], sticker=p["sticker"] or None, duration=p["duration"], z=20)]
    if p["small_label"]:
        out.insert(0, _d.InterviewSmallLabel(p["small_label"], duration=p["duration"], z=21))
    return out


@register("dfsc_interview_name_tag")
def _dfsc_name_tag(p: dict, brand: BrandKit) -> list[Layer]:
    return [_d.InterviewNameTag(p["name"], left_sticker=p["left_sticker"] or None,
                                right_sticker=p["right_sticker"] or None, duration=p["duration"], z=20)]


@register("dfsc_interview_subtitle")
def _dfsc_subtitle(p: dict, brand: BrandKit) -> list[Layer]:
    return [_d.InterviewSubtitle(_cues(p["lines"], 0.0, p["seconds_per_line"]), z=30)]


@register("dfsc_end_card")
def _dfsc_end_card(p: dict, brand: BrandKit) -> list[Layer]:
    return [_d.EndCard(p["edition"], p["theme_zh"], p["theme_en"], p["cta_label"], p["cta_url"],
                       slogan=p["slogan"], invite=p["invite"], name_en=p["name_en"], duration=p["duration"], z=50)]


@register("dfsc_interview_reel")
def _dfsc_interview_reel(p: dict, brand: BrandKit) -> list[Layer]:
    """SOP structure: hook → answer (name tag) → key line → slogan → event invite → end card."""
    seg = p["segment_seconds"]
    t_name, t_key, t_slogan, t_end = seg, 2 * seg, 3 * seg, 4 * seg
    subs = p["subtitles"]
    per = max(t_slogan / max(len(subs), 1), 0.8)
    return [
        _d.InterviewTopLabel(p["hook_label"], sticker=p["hook_sticker"] or None, start=0, duration=seg, z=20),
        _d.InterviewNameTag(p["name"], left_sticker=p["name_left_sticker"] or None,
                            right_sticker=p["name_right_sticker"] or None, start=t_name, duration=seg, z=20),
        _d.InterviewSmallLabel(p["key_small_label"], start=t_key, duration=seg, z=21),
        _d.InterviewBigTitle(p["key_title"], sticker=p["key_sticker"] or None, start=t_key, duration=seg, z=20),
        _d.InterviewSubtitle(_cues(subs, 0.0, per), start=0, z=30),
        _d.InterviewBigTitle(p["slogan"], start=t_slogan, duration=seg, size=130, y=860, z=20),
        _d.InterviewSmallLabel(p["invite"], start=t_slogan, duration=seg, y=1080, size=52, z=21),
        _d.EndCard(p["edition"], p["theme_zh"], p["theme_en"], p["cta_label"], p["cta_url"],
                   start=t_end, duration=p["end_seconds"], z=50),
    ]


@register("dfsc_launch_background")
def _dfsc_launch_bg(p: dict, brand: BrandKit) -> list[Layer]:
    return [_d.LaunchBackground(z=-90, duration=p["duration"]),
            _d.LaunchStar(x=p["star_x"], y=p["star_y"], height=p["star_height"], stem=p["stem"], z=-80,
                          duration=p["duration"])]


@register("dfsc_launch_title")
def _dfsc_launch_title(p: dict, brand: BrandKit) -> list[Layer]:
    out = [_d.LaunchSerifText([p["title"]], y=p["title_y"], size=p["title_size"], duration=p["duration"], z=20)]
    if p["lines"]:
        out.append(_d.LaunchSerifText(p["lines"], y=p["lines_y"], size=64, role="serif_body",
                                      start=0.4, duration=p["duration"] - 0.4, z=20))
    return out


@register("dfsc_launch_alumni_orbit")
def _dfsc_launch_orbit(p: dict, brand: BrandKit) -> list[Layer]:
    return [_d.LaunchStar(x=540, y=900, height=260, stem=False, duration=p["duration"], z=10),
            _d.LaunchAlumniOrbit(p["names"], roles=p["roles"], duration=p["duration"], z=20)]


@register("dfsc_launch_stats")
def _dfsc_launch_stats(p: dict, brand: BrandKit) -> list[Layer]:
    items = [(it["value"], it["label"]) for it in p["items"]]
    return [_d.LaunchStats(items, footer=p["footer"], size=96, duration=p["duration"], z=20)]


@register("dfsc_launch_sequence")
def _dfsc_launch_sequence(p: dict, brand: BrandKit) -> list[Layer]:
    """Film structure (FB 0:00–0:59.5): navy grid + star → serif title → alumni orbit → stats → end card."""
    seg = p["segment_seconds"]
    items = [(it["value"], it["label"]) for it in p["items"]]
    return [
        _d.LaunchBackground(duration=4 * seg, z=-90),
        _d.LaunchStar(x=760, y=420, height=300, stem=False, duration=seg, z=-80),
        _d.LaunchSerifText([p["title"]], y=640, size=190, duration=seg, z=20),
        _d.LaunchSerifText(p["lines"], y=1180, size=64, role="serif_body", start=0.4, duration=seg - 0.4, z=20),
        _d.LaunchStar(x=540, y=900, height=260, stem=False, start=seg, duration=seg, z=10),
        _d.LaunchAlumniOrbit(p["names"], roles=p["roles"], start=seg, duration=seg, z=20),
        _d.LaunchStar(x=760, y=560, height=200, stem=False, start=2 * seg, duration=seg, z=10),
        _d.LaunchStats(items, footer=p["footer"], size=96, start=2 * seg, duration=seg, z=20),
        _d.EndCard(p["edition"], p["theme_zh"], p["theme_en"], p["cta_label"], p["cta_url"],
                   start=3 * seg, duration=p["end_seconds"], z=50),
    ]
