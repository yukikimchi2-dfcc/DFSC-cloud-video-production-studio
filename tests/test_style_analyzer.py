import json

import pytest

import fixtures as fx
from studio.style import profiles as sp
from studio.style.analyzer import analyze_video, write_style_report


@pytest.fixture(scope="module")
def analysis(tmp_path_factory):
    v = fx.multi_shot_video(tmp_path_factory.mktemp("style") / "ref.mp4")
    return analyze_video(v)


def test_shots_and_pacing(analysis):
    e = analysis["editing"]
    assert e["shots"] == 3, e["cut_times"]
    assert [round(c) for c in e["cut_times"]] == [2, 4]
    assert abs(e["average_shot_length"] - 2.0) < 0.2
    assert abs(e["cuts_per_minute"] - 20) < 2


def test_text_audio_colour(analysis):
    assert analysis["text"]["frames_with_text_ratio"] > 0.5
    assert analysis["text"]["zone"] == "bottom"
    assert analysis["audio"]["bpm"] == pytest.approx(120, abs=3)
    assert len(analysis["colour"]["palette"]) == 5


def test_report_and_profile_workflow(analysis, tmp_path):
    md, js = write_style_report(analysis, tmp_path)
    text = md.read_text(encoding="utf-8")
    assert "UNREVIEWED" in text and "需要人工判斷" in text and "自動量測" in text
    data = json.loads(js.read_text(encoding="utf-8"))
    assert data["keyframes"] and (tmp_path / data["keyframes"][0]["file"]).exists()

    root = tmp_path / "profiles"
    p = sp.create_profile_from_analysis(data, "Test_Style", root=root)
    assert p.review_status == "UNREVIEWED"
    assert sp.get_brand_standard(root=root) == []
    with pytest.raises(LookupError):
        sp.get_brand_standard("Test_Style", root=root)
    with pytest.raises(FileExistsError):
        sp.create_profile_from_analysis(data, "Test_Style", root=root)
    with pytest.raises(ValueError):
        sp.set_review_status("Test_Style", "APPROVED", reviewer="")
    sp.set_review_status("Test_Style", "APPROVED", reviewer="QA", note="test", root=root)
    approved = sp.get_brand_standard("Test_Style", root=root)
    assert approved.review_status == "APPROVED" and approved.history[-1]["by"] == "QA"


def test_seeded_categories_are_unreviewed_placeholders():
    profs = {p.name: p for p in sp.load_profiles()}
    for name in ("Fast_Paced_Interview", "Premium_Brand_Story", "Modern_Cinematic", "Playful_Motion_Graphics",
                 "Meta_Lead_Generation", "Event_Promotion", "Product_Sales_Ad"):
        assert profs[name].review_status == "UNREVIEWED" and profs[name].category_only
        assert not profs[name].source_videos


def test_category_cannot_be_approved(tmp_path):
    root = tmp_path / "p"
    sp.save_profile(sp.StyleProfile("Cat", category_only=True), root)
    with pytest.raises(ValueError):
        sp.set_review_status("Cat", "APPROVED", reviewer="x", root=root)
