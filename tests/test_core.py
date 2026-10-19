import numpy as np
import pytest

from studio import versioning
from studio.brand import BrandKit, load_brand
from studio.config import deep_merge, load_config
from studio.core import canvas, easing, vector
from studio.core.canvas import Patch
from studio.core.timeline import FuncLayer, Timeline


def test_deep_merge_project_wins_and_keeps_siblings():
    base = {"render": {"final": {"crf": 16, "fps": "source"}}, "x": 1}
    out = deep_merge(base, {"render": {"final": {"crf": 18}}})
    assert out["render"]["final"] == {"crf": 18, "fps": "source"}
    assert base["render"]["final"]["crf"] == 16  # input untouched


def test_defaults_match_brief():
    cfg = load_config()
    f, p = cfg["render"]["final"], cfg["render"]["preview"]
    assert (f["width"], f["height"], f["crf"], f["audio_bitrate"]) == (1080, 1920, 16, "256k")
    assert (f["loudness_lufs"], f["true_peak_dbtp"]) == (-14.0, -1.5)
    assert (p["width"], p["height"], p["max_size_mb"]) == (720, 1280, 30)


def test_project_override_applies():
    assert load_config("dfsc-2027")["render"]["default_fps"] == 30


@pytest.mark.parametrize("name", sorted(easing.EASINGS))
def test_easing_endpoints(name):
    fn = easing.get(name)
    assert fn(0.0) == pytest.approx(0.0, abs=1e-6)
    assert fn(1.0) == pytest.approx(1.0, abs=1e-6)


def test_composite_alpha_and_clipping():
    frame = canvas.solid(10, 10, "#000000")
    rgba = np.zeros((4, 4, 4), np.float32)
    rgba[..., 0] = 1.0
    rgba[..., 3] = 0.5
    canvas.composite(frame, Patch(rgba, 8, 8))  # half off-frame
    assert frame[9, 9, 0] == pytest.approx(0.5)
    assert frame[7, 7, 0] == 0.0


def test_transform_patch_rotation_keeps_content():
    rgba = np.ones((20, 40, 4), np.float32)
    out = canvas.transform_patch(Patch(rgba, 100, 100), scale=1.0, rotation_deg=90)
    assert abs(out.w - 20) <= 2 and abs(out.h - 40) <= 2
    assert out.rgba[..., 3].sum() == pytest.approx(800, rel=0.05)


def test_hex_to_rgb_forms():
    assert canvas.hex_to_rgb("#47B649") == pytest.approx((71 / 255, 182 / 255, 73 / 255))
    assert canvas.hex_to_rgb((71, 182, 73)) == pytest.approx((71 / 255, 182 / 255, 73 / 255))


def test_star_shape_rasterises_with_holes_respected():
    p = vector.render_shape(vector.star_shape(), 200)
    a = p.rgba[..., 3]
    assert a[100, 100] > 0.99          # centre filled
    assert a[2, 100] < 0.01            # between points (top middle) empty for a 45° rotated star
    ring = {"viewbox": [10, 10], "paths": [{"fill": "#FF0000", "subpaths": [
        [[0, 0], [10, 0], [10, 10], [0, 10]], [[3, 3], [7, 3], [7, 7], [3, 7]]]}]}
    r = vector.render_shape(ring, 100).rgba[..., 3]
    assert r[50, 50] < 0.01 and r[10, 10] > 0.99


def test_versioning_never_overwrites(tmp_path):
    a = versioning.reserve_output(tmp_path, "proj", "preview")
    b = versioning.reserve_output(tmp_path, "proj", "preview")
    c = versioning.reserve_output(tmp_path, "proj", "final")
    assert [p.name for p in (a, b, c)] == ["proj_v001_preview.mp4", "proj_v002_preview.mp4", "proj_v003_final.mp4"]
    assert versioning.parse(c) == {"name": "proj", "version": 3, "mode": "final", "ext": "mp4"}


def test_dfsc_brand_loads_with_extracted_logos():
    b = load_brand("dfsc-2027")
    assert b.color("green") == "#47B649" and b.color("blue") == "#1C61AE"
    assert b.check_fonts() == []
    for key in ("north_star_tricolor", "north_star_black", "qihang_wordmark", "dfsc_lockup"):
        p = vector.render_shape(b.logo_shape(key), 128)
        assert p.rgba[..., 3].max() > 0.99, key
    font = b.font("title", 64)
    assert font.getbbox("啟航北極星")[2] > 64 * 4  # glyphs exist (not tofu-width zero)


def test_unknown_brand_colour_is_a_clear_error():
    with pytest.raises(KeyError, match="no colour"):
        BrandKit.neutral().color("nope")


def test_timeline_layer_order_and_local_time():
    seen = []

    def rec(frame, ctx, t):
        seen.append(round(t, 3))
        return frame

    tl = Timeline(width=16, height=16, fps=10, duration=1.0)
    tl.add(FuncLayer(rec, start=0.5, duration=0.3))
    for i in range(tl.n_frames):
        tl.render_frame(i / tl.fps)
    assert seen == [0.0, 0.1, 0.2]
