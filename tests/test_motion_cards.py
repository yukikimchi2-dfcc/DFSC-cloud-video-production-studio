import numpy as np
import pytest

from studio.brand import BrandKit, load_brand
from studio.core.timeline import FuncLayer, Timeline
from studio.motion import cards

W, H = 270, 480


def render(*layers, t, brand=None, bg="#000000"):
    tl = Timeline(duration=10, background=bg, brand=brand or BrandKit.neutral()).add(*layers)
    return tl.render_frame(t, tl.context(W, H))


@pytest.mark.parametrize("make", [
    lambda: cards.SolidPanel(color="#FF0000"),
    lambda: cards.GradientPanel(color_from="#FF0000", color_to="#0000FF"),
    lambda: cards.ExpandableTitleCard("標題", "副標題", color="#FF0000"),
    lambda: cards.ImpactCard("衝擊", color="#FF0000"),
    lambda: cards.StatCard(1200, label="人", color="#FF0000"),
    lambda: cards.QuoteCard("金句測試", author="某人", color="#FF0000"),
    lambda: cards.CTACard("立即報名", color="#FF0000"),
    lambda: cards.BrandLockupCard(color="#FF0000", panel=True),
])
def test_cards_render_panel_in_safe_area(make):
    card = make()
    f = render(card, t=3.0)
    red = (f[..., 0] > 0.8) & (f[..., 1] < 0.3) & (f[..., 2] < 0.3)
    if isinstance(card, cards.GradientPanel):
        red = f.sum(axis=2) > 0.5
    assert red.sum() > 200
    ys, xs = np.nonzero(red)
    from studio.core.timeline import RenderContext
    sx0, sy0, sx1, sy1 = RenderContext(W, H, 30, scale=H / 1920).safe_rect()
    assert xs.min() >= sx0 - 3 and xs.max() <= sx1 + 3 and ys.min() >= sy0 - 3 and ys.max() <= sy1 + 3


def test_card_enter_and_exit():
    card = cards.SolidPanel(color="#FF0000", enter="slide_up", duration=2.0, exit="fade")
    assert render(card, t=0.0).max() < 0.05
    assert render(card, t=1.0)[..., 0].max() > 0.9
    assert render(card, t=1.99)[..., 0].max() < 0.1


def test_stat_counter_counts_up():
    card = cards.StatCard(1200, prefix="NT$", suffix="+")
    assert card.number_text(0) == "NT$0+"
    assert card.number_text(10) == "NT$1,200+"
    mid = card.number_text(0.3)
    assert mid != "NT$0+" and mid != "NT$1,200+"


def test_glass_panel_blurs_background():
    def stripes(frame, ctx, t):
        frame[:, ::2] = 1.0
        frame[:, 1::2] = 0.0
        return frame
    f = render(FuncLayer(stripes, z=-1), cards.GlassPanel(x=90, y=800, w=900, h=300, tint_opacity=0.0, border=None), t=3)
    inside = f[int(900 / 1920 * H), 60:200, 0]
    outside = f[20, 60:200, 0]
    assert inside.std() < outside.std() * 0.3


def test_brand_lockup_uses_brand_logo():
    f = render(cards.BrandLockupCard(logo="dfsc_lockup", color="#FFFFFF", panel=True), t=3, brand=load_brand("dfsc-2027"))
    green = (f[..., 1] > 0.6) & (f[..., 0] < 0.4)
    assert green.sum() > 30  # the green English line / paper plane of the lockup


def test_quote_mark_does_not_overlap_quote_text():
    """Regression: the 「 mark used to run into the first line of the quote."""
    import numpy as np
    from studio.brand import BrandKit
    from studio.core.timeline import RenderContext
    from studio.motion.cards import QuoteCard
    card = QuoteCard("創業不是一個人的旅程，而是一群人的啟航。", author="評審", x=90, y=700, w=900, h=420)
    ctx = RenderContext(1080, 1920, 30, brand=BrandKit.neutral())
    mark, text = card.kids[0], card.kids[1]

    def ink_rows(layer):
        p = layer.render(ctx, 3.0)
        rows = np.where(p.rgba[..., 3].max(axis=1) > 0.2)[0]
        return p.y + rows.min(), p.y + rows.max()

    mark_top, mark_bottom = ink_rows(mark)
    text_top, _ = ink_rows(text)
    assert mark_bottom < text_top, (mark_bottom, text_top)
