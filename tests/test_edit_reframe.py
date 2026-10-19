import numpy as np

from fixtures import landscape_video
from studio.core.io import probe
from studio.edit import reframe as rf


def test_crop_size_vertical_from_landscape():
    w, h = rf.crop_size(1920, 1080, 1080, 1920)
    assert h == 1080 and abs(w - 607.5) < 1e-6


def test_smoothing_removes_jitter_and_follows():
    rng = np.random.default_rng(0)
    targets = [(i * 0.5, 500 + rng.normal(0, 8), 300 + rng.normal(0, 8)) for i in range(20)]
    targets += [(10 + i * 0.5, 900.0, 300.0) for i in range(20)]
    out = rf.smooth_path(targets, dead_zone=20)
    xs = np.array([p[1] for p in out])
    assert np.std(np.diff(xs[:20])) < 2.0          # jitter inside dead zone ignored
    assert abs(xs[-1] - 900) < 25                  # follows the real move (within dead zone)
    assert np.max(np.abs(np.diff(xs))) < 200       # no snapping


def test_crop_path_bounds_and_render(tmp_path):
    v = landscape_video(tmp_path / "wide.mp4", 2.0)
    # synthetic detections: face drifts to the far right edge, then disappears
    dets = [(0.0, (300, 100, 60, 60)), (0.5, (560, 100, 60, 60)), (1.0, (600, 100, 40, 40)), (1.5, None)]
    cp = rf.build_crop_path(v, 360, 640, detections=dets, push_in=0.1)
    for k in cp.keys:
        assert k.cx - k.w / 2 >= -1e-6 and k.cx + k.w / 2 <= 640 + 1e-6
        assert k.cy - k.h / 2 >= -1e-6 and k.cy + k.h / 2 <= 360 + 1e-6
    assert cp.keys[-1].w < cp.keys[0].w            # push-in
    back = rf.CropPath.load(cp.save(tmp_path / "crop.json"))
    assert back.keys == cp.keys
    out = rf.render_reframe(cp, tmp_path / "vert.mp4")
    info = probe(out)
    assert (info.width, info.height) == (360, 640) and info.has_audio


def test_face_in_safe_area():
    k = rf.CropKey(0, 500, 500, 400, 800)
    assert rf.face_in_safe_area((450, 300, 100, 100), k, {"top": 0.1, "bottom": 0.18, "left": 0.06, "right": 0.12})
    assert not rf.face_in_safe_area((300, 120, 100, 100), k, {"top": 0.1, "left": 0.06})
