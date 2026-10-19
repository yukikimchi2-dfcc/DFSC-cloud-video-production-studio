import numpy as np
import pytest

from studio.brand import BrandKit
from studio.core.timeline import FuncLayer, SolidLayer, Timeline
from studio.motion import particles
from studio.motion.stickers import StickerLayer, add_outline, emoji_image

W, H = 135, 240


def render(*layers, t=1.0, bg="#000000"):
    tl = Timeline(duration=5, background=bg, brand=BrandKit.neutral()).add(*layers)
    return tl.render_frame(t, tl.context(W, H))


@pytest.mark.parametrize("layer", [
    particles.StarSparkles(count=20, size_range=(60, 120)),
    particles.LightDots(count=30, size_range=(60, 100), intensity=0.8),
    particles.ParticleEmitter(burst=40, rate=0, size=(40, 80)),
    particles.ShapeLayer("star", size=400), particles.ShapeLayer("ring", size=400),
    particles.GuideRectLayer(rect=(100, 100, 800, 1200), thickness=12),
    particles.PanelWipeLayer(color="#FFFFFF"),
    particles.EllipseRingLayer(thickness=40),
])
def test_particle_layers_draw_something(layer):
    assert render(layer, t=0.8).max() > 0.3


def test_emitter_is_deterministic_and_seekable():
    e = particles.ParticleEmitter(burst=30, rate=20, seed=4)
    a = render(e, t=0.7)
    render(e, t=0.1)  # render out of order
    assert np.array_equal(a, render(e, t=0.7))


def test_frame_effects():
    grey = SolidLayer("#808080")
    assert render(grey, particles.Vignette(strength=0.8))[0, 0].mean() < render(grey)[0, 0].mean()
    def half(frame, ctx, t):
        frame[:, : frame.shape[1] // 2] = 1.0
        return frame
    ca = render(FuncLayer(half), particles.ChromaticAberration(amount=40))
    assert not np.allclose(ca[..., 0], ca[..., 2])
    assert render(FuncLayer(half), particles.Glow(threshold=0.5)).mean() > render(FuncLayer(half)).mean()


def test_speed_ramp_integrates():
    assert particles.speed_ramp(1.0, [(0, 1.0)]) == pytest.approx(1.0)
    assert particles.speed_ramp(2.0, [(0, 1.0), (1, 1.0), (1.0001, 0.5)]) == pytest.approx(1.5, abs=1e-3)
    assert particles.speed_ramp(1.0, [(0, 0.0), (1, 2.0)]) == pytest.approx(1.0)


def test_emoji_sticker_is_colour_noto():
    img = emoji_image("🚀")
    assert img.shape[0] > 80 and img[..., 3].max() > 0.9
    assert img[..., :3].std() > 0.1  # colour glyph, not a monochrome fallback


def test_outline_grows_alpha():
    img = np.zeros((40, 40, 4), np.float32)
    img[15:25, 15:25] = 1.0
    out = add_outline(img, 5)
    assert out[..., 3].sum() > img[..., 3].sum() * 1.5


def test_sticker_pops_in_and_flies_out():
    s = StickerLayer("🎉", height=600, duration=2.0, exit="fly_right", exit_duration=0.3)
    assert render(s, t=0.0).max() < 0.05
    assert render(s, t=1.0).max() > 0.5
    assert render(s, t=1.99).max() < 0.05
