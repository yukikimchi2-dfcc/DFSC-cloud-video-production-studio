import numpy as np
import pytest

from studio.brand import BrandKit, load_brand
from studio.core.timeline import RenderContext, Timeline
from studio.motion._util import get_font
from studio.motion.typography import TextLayer, WordHighlightLayer, tokenize, wrap_text

W, H = 270, 480


def ctx(brand=None):
    return RenderContext(W, H, 30, brand=brand or BrandKit.neutral(), scale=H / 1920)


def frame_with(*layers, t=5.0, bg="#000000", brand=None):
    tl = Timeline(duration=10, background=bg, brand=brand or BrandKit.neutral()).add(*layers)
    return tl.render_frame(t, tl.context(W, H))


def test_font_has_traditional_chinese_glyphs():
    font = get_font(BrandKit.neutral(), "title", 64)
    for ch in "啟航北極星屆夢場賽":
        bbox = font.getbbox(ch)
        assert bbox[2] - bbox[0] > 20, f"glyph {ch} missing"
    assert "TC" in " ".join(font.getname()) or "HK" in " ".join(font.getname())


def test_cjk_tokenize_and_kinsoku_wrap():
    assert tokenize("啟航 North Star") == ["啟", "航", " ", "North ", "Star"]
    font = get_font(None, "body", 40)
    lines = wrap_text("一二三四五六七八九十，好", font, max_width=font.getlength("一") * 10)
    assert all(not l.startswith("，") for l in lines)
    assert lines[0].endswith("，")  # punctuation pulled back onto the previous line


def test_text_renders_inside_safe_area():
    f = frame_with(TextLayer("啟航 北極星 Find Your North Star 這是一段很長的字幕需要自動換行", y=100, size=90,
                             color="#FFFFFF", animation="none"))
    ys, xs = np.nonzero(f.max(axis=2) > 0.5)
    c = ctx()
    x0, y0, x1, y1 = c.safe_rect()
    assert len(xs) > 500
    assert xs.min() >= x0 - 2 and xs.max() <= x1 + 2
    assert ys.min() >= y0 - 2


def test_typewriter_reveals_progressively():
    layer = TextLayer("一二三四五六", size=120, animation="typewriter", stagger=0.2, color="#FFFFFF")
    counts = [int((frame_with(layer, t=t).max(axis=2) > 0.5).sum()) for t in (0.0, 0.5, 2.0)]
    assert counts[0] < counts[1] < counts[2]


@pytest.mark.parametrize("anim", ["fade", "bounce", "rotate", "fly_in", "slam", "scale", "pop", "drop"])
def test_char_animations_settle_to_static(anim):
    static = frame_with(TextLayer("北極星", size=120, animation="none", color="#FFFFFF"))
    animated = frame_with(TextLayer("北極星", size=120, animation=anim, color="#FFFFFF"), t=5.0)
    assert np.abs(static - animated).mean() < 0.002


def test_exit_removes_text():
    layer = TextLayer("再見", size=120, color="#FFFFFF", duration=2.0, exit="fade", exit_duration=0.3)
    assert frame_with(layer, t=1.99).max() < 0.05


def test_stroke_shadow_gradient_underline_sweep_vertical_render():
    layers = [
        TextLayer("描邊", y=200, size=120, stroke=8, stroke_color="#FF0000", color="#FFFFFF", animation="none"),
        TextLayer("漸層", y=500, size=120, gradient={"from": "#FF0000", "to": "#0000FF"}, animation="none",
                  underline={"color": "#00FF00", "start": 0, "duration": 0.1}, sweep={"start": 4.8, "duration": 0.5}),
        TextLayer("第十一屆", x=150, y=900, size=80, vertical=True, color="#FFFFFF", animation="none", shadow={"blur": 6}),
    ]
    f = frame_with(*layers)
    assert (f[..., 0] > 0.8).sum() > 50 and (f[..., 2] > 0.6).sum() > 20 and (f[..., 1] > 0.8).sum() > 20
    v = layers[2].bbox(ctx())
    assert (v[3] - v[1]) > 3 * (v[2] - v[0])  # vertical stack is tall and narrow


def test_word_highlight_colours_active_word():
    words = [{"text": "創業", "start": 0, "end": 1}, {"text": "啟航", "start": 1, "end": 2}]
    layer = WordHighlightLayer(words, color="#FFFFFF", highlight_color="#FF0000", stroke=0, y=900)
    red_first = (frame_with(layer, t=0.5)[..., 1] < 0.3) & (frame_with(layer, t=0.5)[..., 0] > 0.8)
    xs = np.nonzero(red_first)[1]
    xs2 = np.nonzero((frame_with(layer, t=1.5)[..., 1] < 0.3) & (frame_with(layer, t=1.5)[..., 0] > 0.8))[1]
    assert len(xs) > 30 and len(xs2) > 30 and xs.mean() < xs2.mean()


def test_dfsc_brand_fonts_resolve():
    brand = load_brand("dfsc-2027")
    for role in ("title", "heading", "body", "subtitle", "numerals_thin"):
        assert get_font(brand, role, 40).getbbox("啟")[2] > 10
