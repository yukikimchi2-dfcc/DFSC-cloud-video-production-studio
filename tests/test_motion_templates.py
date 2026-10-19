import json
from pathlib import Path

import pytest

from studio.brand import BrandKit, load_brand
from studio.core.timeline import Timeline
from studio.motion.templates import (TemplateError, build_template, get_template, list_templates,
                                     preview_timeline, render_template_preview, template_duration)

TEMPLATES = [t["id"] for t in list_templates()]
REQUIRED = {"id", "name", "version", "category", "review_status", "description", "usage", "parameters", "test_record"}


def test_registry_has_required_templates():
    for tid in ["title_card_impact", "lower_third_basic", "stat_counter", "quote_card", "cta_card_end",
                "brand_lockup_outro", "subtitle_word_highlight", "dfsc2027_north_star_open"]:
        assert tid in TEMPLATES


@pytest.mark.parametrize("tid", TEMPLATES)
def test_template_metadata_complete(tid):
    meta = get_template(tid)
    assert REQUIRED <= set(meta), REQUIRED - set(meta)
    assert meta["review_status"] in ("APPROVED", "REFERENCE ONLY", "REJECTED", "UNREVIEWED")
    for p in meta["parameters"]:
        assert {"name", "type", "default", "description"} <= set(p)
    d = Path(meta["_dir"])
    assert (d / "preview.png").exists() and (d / "preview.gif").exists(), "run tools/demo_motion.py --previews"
    assert (d / "preview.gif").stat().st_size <= 1_500_000
    assert json.loads((d / "test_record.json").read_text(encoding="utf-8"))["passed"]


@pytest.mark.parametrize("tid", TEMPLATES)
@pytest.mark.parametrize("project", [None, "dfsc-2027"])
def test_template_builds_and_renders(tid, project):
    req = get_template(tid).get("requires_project")
    if req and project != req:
        pytest.skip(f"{tid} uses {req} brand colours")
    brand = load_brand(project)
    tl = preview_timeline(tid, brand, width=135, height=240)
    ctx = tl.context(135, 240)
    frames = [tl.render_frame(t, ctx) for t in (0.0, tl.duration * 0.6, tl.duration - 0.05)]
    assert frames[1].std() > 0.01  # mid-template frame has visible content


def test_unknown_param_rejected():
    with pytest.raises(TemplateError):
        build_template("stat_counter", {"nope": 1})
    with pytest.raises(TemplateError):
        get_template("does_not_exist")


def test_dfsc_template_is_unreviewed():
    assert get_template("dfsc2027_north_star_open")["review_status"] == "UNREVIEWED"


def test_render_preview_to_tmp(tmp_path):
    r = render_template_preview("stat_counter", tmp_path, width=135, height=240, gif_width=68, gif_fps=4)
    assert Path(r["png"]).exists() and Path(r["gif"]).exists() and r["record"]["passed"]
    assert template_duration("stat_counter") == 3.0
