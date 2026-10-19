import json

import pytest

from studio.config import load_config
from studio.core.io import probe
from studio.render import queue as Q
from studio.render.demo import build_test_card, make_test_tone
from studio.render.renderer import Renderer, render_history

pytestmark = pytest.mark.slow


@pytest.fixture
def cfg(tmp_path):
    return load_config("dfsc-2027", overrides={
        "studio": {"workspace_dir": str(tmp_path / "ws"), "renders_dir": str(tmp_path / "renders")},
        # shrink renders so the suite stays fast; ratios and code paths are unchanged
        "render": {"preview": {"width": 180, "height": 320}, "final": {"width": 270, "height": 480, "preset": "ultrafast"}},
        "_retry_delay_scale": 0.0,
    })


def test_preview_render_versions_and_record(cfg, tmp_path):
    r = Renderer("dfsc-2027", cfg, out_dir=tmp_path / "out")
    a = r.render(build_test_card(duration=1.0), "preview", name="t")
    b = r.render(build_test_card(duration=1.0), "preview", name="t", start=0.2, end=0.6)
    assert a.path.endswith("t_v001_preview.mp4") and b.path.endswith("t_v002_preview.mp4")
    assert (a.width, a.height) == (180, 320)
    assert b.duration == pytest.approx(0.4, abs=0.07)
    hist = render_history(tmp_path / "out")
    assert [h["version"] for h in hist] == [1, 2]
    assert json.loads((tmp_path / "out" / "t_v001_preview.json").read_text())["project_id"] == "dfsc-2027"


def test_final_render_hits_loudness_target(cfg, tmp_path):
    tone = make_test_tone(tmp_path / "tone.wav", duration=3.0)
    r = Renderer("dfsc-2027", cfg, out_dir=tmp_path / "out")
    res = r.render(build_test_card(duration=3.0, audio=tone), "final", name="loud")
    info = probe(res.path)
    assert info.acodec == "aac" and info.has_video
    assert res.audio["target_lufs"] == -14.0
    from studio.render.renderer import loudnorm  # re-measure the delivered file
    stats = loudnorm(res.path, tmp_path / "check.mp4", -14.0, -1.5)
    assert stats["measured_input_lufs"] == pytest.approx(-14.0, abs=1.0)
    assert stats["measured_input_tp"] <= -1.0


def test_preview_size_cap_raises_crf(cfg, tmp_path):
    cfg["render"]["preview"]["max_size_mb"] = 0.005  # absurdly small -> forces re-encodes
    res = Renderer("dfsc-2027", cfg, out_dir=tmp_path / "out").render(build_test_card(duration=1.0), "preview")
    assert res.crf > 26


def test_queue_retries_then_fails_with_log(cfg):
    job = Q.enqueue("studio.render.demo:does_not_exist", {}, max_attempts=2, cfg=cfg)
    done = Q.run_job(job, cfg)
    assert done["state"] == "failed" and done["attempts"] == 2
    assert len(done["history"]) == 2 and "AttributeError" in done["error"]
    log = (Q.queue_dir(cfg) / f"{job['id']}.log").read_text()
    assert log.count("FAILED") == 2


def test_queue_chunk_cache_and_partial_rerender(cfg):
    kwargs = {"duration": 2.0}
    j1 = Q.run_job(Q.enqueue("studio.render.demo:build_test_card", kwargs, name="c", project_id="dfsc-2027",
                             chunk_seconds=0.5, cfg=cfg), cfg)
    assert j1["state"] == "done", j1["error"]
    assert len(j1["chunks_rendered"]) == 4
    j2 = Q.run_job(Q.enqueue("studio.render.demo:build_test_card", kwargs, name="c", project_id="dfsc-2027",
                             chunk_seconds=0.5, invalidate=[(0.6, 0.9)], cfg=cfg), cfg)
    assert j2["chunks_rendered"] == [[0.5, 1.0]]          # only the touched chunk re-rendered
    assert len(j2["chunks_cached"]) == 3
    assert probe(j2["result"]["path"]).duration == pytest.approx(2.0, abs=0.1)
    assert j1["result"]["path"] != j2["result"]["path"]   # new version, old one kept
