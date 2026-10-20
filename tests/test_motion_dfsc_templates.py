"""DFSC template families (interview Reel / launch film) built from the reference edits."""
import numpy as np
import pytest

from studio.brand import load_brand
from studio.motion import dfsc
from studio.motion.templates import get_template, list_templates, preview_timeline, template_duration

DFSC = sorted(t["id"] for t in list_templates() if t["id"].startswith("dfsc_"))


@pytest.fixture(scope="module")
def brand():
    return load_brand("dfsc-2027")


def _param(tid, name):
    return next(p["default"] for p in get_template(tid)["parameters"] if p["name"] == name)


def test_both_families_registered():
    for tid in ("dfsc_interview_top_label", "dfsc_interview_big_title", "dfsc_interview_name_tag",
                "dfsc_interview_subtitle", "dfsc_interview_reel", "dfsc_end_card", "dfsc_launch_background",
                "dfsc_launch_title", "dfsc_launch_alumni_orbit", "dfsc_launch_stats", "dfsc_launch_sequence"):
        assert tid in DFSC


@pytest.mark.parametrize("tid", DFSC)
def test_reference_only_with_sources(tid):
    meta = get_template(tid)
    assert meta["review_status"] == "REFERENCE ONLY"  # user-authorised baseline, not per-item approval
    assert "非逐项审美批准" in meta["review_note"]
    assert meta["sources"] and all({"video", "timecode"} <= set(s) for s in meta["sources"])


@pytest.mark.parametrize("tid", DFSC)
def test_renders_non_empty(tid, brand):
    tl = preview_timeline(tid, brand, width=270, height=480)
    frame = tl.render_frame(min(get_template(tid)["preview"]["time"], tl.duration - 0.05), tl.context(270, 480))
    assert frame.shape == (480, 270, 3) and frame.std() > 0.02


@pytest.mark.parametrize("tid", ["dfsc_interview_reel", "dfsc_launch_sequence"])
def test_sequences_have_no_empty_tail(tid, brand):
    tl = preview_timeline(tid, brand, width=270, height=480)
    assert template_duration(tid, {}) == pytest.approx(get_template(tid)["duration"])
    ctx = tl.context(270, 480)
    for t in np.arange(0.5, tl.duration, 0.5):
        assert tl.render_frame(float(t), ctx).mean() > 0.03, f"black frame at {t}s"


def test_unsourced_copy_is_placeholder():
    assert _param("dfsc_interview_reel", "slogan").startswith("〔")
    assert _param("dfsc_interview_reel", "invite").startswith("〔")
    assert _param("dfsc_interview_reel", "name").startswith("〔")
    assert all(r.startswith("〔") for r in _param("dfsc_launch_sequence", "roles"))
    assert _param("dfsc_end_card", "slogan") in ("", None) or _param("dfsc_end_card", "slogan").startswith("〔")


def test_subtitle_inside_safe_area(brand):
    layer = dfsc.InterviewSubtitle([(0, 1, "示例字幕[關鍵詞]")])
    assert 1920 * 0.10 < layer.y < 1920 * 0.80  # clear of Reels UI at the bottom
    assert layer.active_cue(0.5) and layer.active_cue(1.5) is None


def test_sampled_colours_present(brand):
    for name, hexv in {"ref_keyword_green": "#6CD76B", "ref_label_navy_top": "#10223E",
                       "ref_endcard_bg": "#EDEDED", "ref_cloud_green": "#4DAC54", "ref_launch_navy": "#071C3C"}.items():
        assert brand.color(name).upper() == hexv
    tl = preview_timeline("dfsc_end_card", brand, width=270, height=480)
    corner = tl.render_frame(3.0, tl.context(270, 480))[240, 5] * 255  # left edge mid-height: card background
    assert np.abs(corner - np.array([0xED, 0xED, 0xED])).max() < 12


def test_parse_marked():
    assert dfsc.parse_marked("在還沒有參加[圓夢]之前") == [("在還沒有參加", False), ("圓夢", True), ("之前", False)]
    assert dfsc.parse_marked("[全部]") == [("全部", True)]
    assert dfsc.parse_marked("沒有標記") == [("沒有標記", False)]


# ---- interview components used by real edits (projects/dfsc-2027/edits/*): variants seen in the reference reels

def _ctx(brand):
    from studio.core.timeline import Timeline
    return Timeline(1080, 1920, 30, brand=brand).context()


def test_name_tag_subline_extends_down_without_moving_plate(brand):
    ctx = _ctx(brand)
    plain = dfsc.InterviewNameTag("Nelson Chin", right_sticker="🍵")
    sub = dfsc.InterviewNameTag("Nelson Chin", right_sticker="🍵", subline="五告凉 · 第十屆參賽者")
    a, b = plain._get(ctx), sub._get(ctx)
    assert b.h > a.h
    fa = plain.draw(np.zeros((1920, 1080, 3), np.float32), ctx, 1.0)
    fb = sub.draw(np.zeros((1920, 1080, 3), np.float32), ctx, 1.0)
    rows = lambda f: np.where(f.max(axis=(1, 2)) > 0.05)[0]       # noqa: E731
    assert rows(fa)[0] == rows(fb)[0] and rows(fb)[-1] > rows(fa)[-1]


def test_top_label_green_style_and_left_sticker(brand):
    ctx = _ctx(brand)
    navy = dfsc.InterviewTopLabel("看到這個商機", size=72)._get(ctx)
    green = dfsc.InterviewTopLabel("看到這個商機", size=72, style="green", sticker="💡", sticker_side="left")._get(ctx)
    mid = lambda p: p.rgba[p.h // 2, p.w // 2, :3]                 # noqa: E731
    assert mid(green)[1] > mid(green)[0] + 0.2 and mid(navy)[2] > mid(navy)[1]


def test_big_title_colour_and_question_pill_and_flash(brand):
    ctx = _ctx(brand)
    red = dfsc.InterviewBigTitle("不歸路", color="#E53935", role="title", size=120)._get(ctx)
    px = red.rgba[red.rgba[..., 3] > 0.99][:, :3]
    assert (px[:, 0] - px[:, 1] > 0.5).any()                        # red fill present
    pill = dfsc.InterviewQuestionPill("創業還是打工？")._get(ctx)
    assert pill.w > pill.h and 0.6 < pill.rgba[pill.h // 2, 5, 3] < 0.9   # translucent body
    flash = dfsc.WhiteFlash()
    f = flash.draw(np.zeros((4, 4, 3), np.float32), ctx, flash.rise + flash.hold / 2)
    assert f.mean() > 0.9 and flash.draw(np.zeros((4, 4, 3), np.float32), ctx, flash.duration).mean() < 0.01


def test_subtitle_pop_in_fades_in_then_settles(brand):
    ctx = _ctx(brand)
    cues = [(0.0, 2.0, "我在賣[涼茶]")]
    draw = lambda layer, t: layer.draw(np.zeros((1920, 1080, 3), np.float32), ctx, t)   # noqa: E731
    pop, plain = dfsc.InterviewSubtitle(cues, pop=0.12), dfsc.InterviewSubtitle(cues)
    assert draw(pop, 0.03).max() < 0.6 < draw(pop, 1.0).max()
    assert np.allclose(draw(pop, 1.0), draw(plain, 1.0))                # settles to the reference style


def test_zoom_punch_attack_hold_release(brand):
    from studio.motion.camera import ZoomPunch
    ctx = _ctx(brand)
    zp = ZoomPunch(amount=0.08, attack=0.12, release=0.25, duration=2.0)
    z = lambda t: zp.camera(t, ctx)[0]                                   # noqa: E731
    assert z(0.0) == pytest.approx(1.0) and z(1.0) == pytest.approx(1.08) and z(2.0) == pytest.approx(1.0)
