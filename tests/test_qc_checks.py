import json

import pytest

import fixtures as fx
from studio.brand import BrandKit
from studio.config import load_config
from studio.qc import checks
from studio.qc.checks import FAIL, PASS, SKIP, WARN, run_qc
from studio.qc.report import write_report


@pytest.fixture(scope="module")
def media(tmp_path_factory):
    d = tmp_path_factory.mktemp("qc")
    return {"clean": fx.clean_video(d / "clean.mp4", 3.0), "black": fx.video_with_black(d / "black.mp4"),
            "freeze": fx.video_with_freeze(d / "freeze.mp4"), "clip": fx.clipping_video(d / "clip.mp4")}


def test_clean_media_passes(media, tmp_path):
    r = run_qc(media["clean"], expected={"width": 320, "height": 240, "fps": 25, "acodec": "aac", "duration": 3.0},
               brand=BrandKit.neutral())
    statuses = {c.name: c.status for c in r.checks}
    assert r.passed, statuses
    for name in ("black_frames", "frozen_frames", "duplicate_frames", "audio_peak", "resolution", "frame_rate",
                 "video_codec", "pixel_format", "duration", "fonts"):
        assert statuses[name] == PASS, name
    assert statuses["subtitle_safe_area"] == SKIP
    md, js = write_report(r, tmp_path)
    assert "QC Report" in md.read_text(encoding="utf-8") and "通過" in md.read_text(encoding="utf-8")
    assert json.loads(js.read_text())["passed"] is True


def test_black_frames_detected(media):
    r = run_qc(media["black"])
    c = r.by_name("black_frames")
    assert c.status == FAIL and abs(c.value[0][0] - 1.0) < 0.1 and not r.passed


def test_freeze_and_duplicates_detected(media):
    r = run_qc(media["freeze"])
    assert r.by_name("frozen_frames").status == WARN
    assert r.by_name("duplicate_frames").status == WARN          # could be an intentional hold
    assert r.by_name("duplicate_frames").value["longest_run"] >= 30
    assert run_qc(media["freeze"], strict_motion=True).by_name("duplicate_frames").status == FAIL


def test_clipping_detected(media):
    assert run_qc(media["clip"]).by_name("audio_peak").status == FAIL


def test_format_mismatch_fails(media):
    r = run_qc(media["clean"], expected={"width": 1080, "height": 1920, "fps": 30})
    assert r.by_name("resolution").status == FAIL and r.by_name("frame_rate").status == FAIL


def test_loudness_check(media):
    c = run_qc(media["clean"], loudness_target=-14).by_name("loudness")
    assert c.status in (WARN, FAIL)    # -18 dBFS tone is not at -14 LUFS


def test_subtitle_safe_area():
    safe = load_config()["safe_area"]
    ok = checks.check_subtitle_safe_area([(0, 100, 1200, 900, 1500)], 1080, 1920, safe)
    bad = checks.check_subtitle_safe_area([(0, 100, 1700, 900, 1800)], 1080, 1920, safe)
    assert ok.status == PASS and bad.status == FAIL


def test_missing_fonts():
    b = BrandKit.neutral()
    b.fonts["title"] = {"path": "/nonexistent/font.otf"}
    assert checks.check_fonts(b).status == FAIL
    assert checks.check_fonts(BrandKit.neutral()).status == PASS


def test_face_occlusion():
    faces = [(1.0, 400, 300, 600, 500)]
    assert checks.check_face_occlusion(faces, [(1.0, 0, 0, 1080, 200)]).status == PASS
    assert checks.check_face_occlusion(faces, [(1.0, 350, 350, 700, 600)]).status == FAIL
    assert checks.check_face_occlusion(faces, [(2.0, 350, 350, 700, 600)]).status == PASS
