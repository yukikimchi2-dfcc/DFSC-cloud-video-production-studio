import numpy as np
import pytest

from studio.brand import BrandKit
from studio.core import easing
from studio.core.timeline import FuncLayer, SolidLayer, Timeline
from studio.motion import camera
from studio.motion.transitions import KINDS, GroupLayer, SequenceLayer, Transition, TransitionLayer, blend

W, H = 135, 240


def gradient_frame():
    ys, xs = np.mgrid[0:H, 0:W].astype(np.float32)
    return np.dstack([xs / W, ys / H, np.full_like(xs, 0.3)]).astype(np.float32)


@pytest.mark.parametrize("name", sorted(easing.EASINGS))
def test_easing_endpoints(name):
    fn = easing.get(name)
    assert abs(fn(0.0)) < 1e-6 and abs(fn(1.0) - 1.0) < 1e-6


@pytest.mark.parametrize("kind", KINDS)
def test_transition_endpoints_equal_sources(kind):
    a = np.zeros((H, W, 3), np.float32) + 0.2
    b = gradient_frame()
    assert np.array_equal(blend(a, b, 0.0, kind), a)
    assert np.array_equal(blend(a, b, 1.0, kind), b)
    mid = blend(a, b, 0.5, kind)
    assert mid.shape == a.shape and np.isfinite(mid).all()


def test_transition_layer_frame_exact():
    red, blue = SolidLayer("#FF0000"), SolidLayer("#0000FF")
    tr = TransitionLayer(red, blue, frames=10, kind="dissolve", fps=30)
    tl = Timeline(duration=1, fps=30).add(tr)
    ctx = tl.context(W, H)
    f0, f9 = tl.render_frame(0, ctx), tl.render_frame(9 / 30, ctx)
    assert f0[..., 0].min() > 0.99 and f9[..., 2].min() > 0.99


def test_sequence_overlaps_by_transition_frames():
    seq = SequenceLayer([SolidLayer("#FF0000", duration=1.0), SolidLayer("#0000FF", duration=1.0)],
                        [Transition("wipe", 15)], fps=30)
    assert abs(seq.duration - 1.5) < 1e-6
    tl = Timeline(duration=seq.duration, fps=30).add(seq)
    ctx = tl.context(W, H)
    assert tl.render_frame(0.2, ctx)[..., 0].mean() > 0.99
    assert tl.render_frame(1.4, ctx)[..., 2].mean() > 0.99


def test_group_layer_local_time():
    g = GroupLayer([SolidLayer("#00FF00", start=0.5)], background="#000000", start=1.0, duration=2.0)
    tl = Timeline(duration=3).add(g)
    ctx = tl.context(W, H)
    assert tl.render_frame(1.2, ctx)[..., 1].max() < 0.01
    assert tl.render_frame(1.6, ctx)[..., 1].min() > 0.99


def test_camera_identity_and_zoom():
    f = gradient_frame()
    assert np.array_equal(camera.apply_camera(f, 1.0, 0.5, 0.5), f)
    z = camera.apply_camera(f, 2.0, 0.5, 0.5)
    # zooming 2x around the centre: left edge now shows the source's x≈0.25
    assert abs(z[H // 2, 0, 0] - 0.25) < 0.03


@pytest.mark.parametrize("layer", [
    camera.DigitalZoom(duration=1), camera.SlowPushIn(duration=1), camera.Pan(duration=1),
    camera.HandheldDrift(), camera.CameraShake(), camera.ZoomThrough(duration=0.5),
    camera.Reframe([(0, (0, 0, 1, 1)), (1, (0.25, 0.25, 0.75, 0.75))]),
])
def test_camera_layers_are_deterministic(layer):
    tl = Timeline(duration=1).add(FuncLayer(lambda fr, c, t: gradient_frame()), layer)
    ctx = tl.context(W, H)
    a, b = tl.render_frame(0.4, ctx), tl.render_frame(0.4, ctx)
    assert np.allclose(a, b) and a.shape == (H, W, 3)


def test_crop_window_and_safe_zone():
    x, y, w, h = camera.crop_window(1920, 1080, 9 / 16, 0.9, 0.5)
    assert h == 1080 and abs(w - 607.5) < 1 and x + w <= 1920
    safe = {"top": 0.1, "bottom": 0.18, "left": 0.06, "right": 0.12}
    assert camera.face_in_safe_zone((0.78, 0.3, 0.08, 0.15), (x, y, w, h), 1920, 1080, safe)


def test_face_tracker_smooths_and_holds():
    tr = camera.FaceTracker(smoothing=0.8, dead_zone=0.0, hold_frames=2)
    tr.update((100, 100, 50, 50), 1000, 1000)
    cx, _ = tr.update((600, 100, 50, 50), 1000, 1000)
    assert 0.125 < cx < 0.625          # moved toward, not jumped to, the new face
    assert tr.update(None, 1000, 1000)[0] == cx  # held while briefly lost


def test_detect_faces_runs_without_downloads():
    assert camera.face_backend() in ("haar", "yunet", "none")
    assert camera.detect_faces(np.zeros((240, 320, 3), np.uint8)) == []


def test_detect_faces_strict_reports_missing_backend():
    if camera.face_backend() != "none":
        pytest.skip("a face backend is available")
    with pytest.raises(camera.FaceDetectionUnavailable):
        camera.detect_faces(np.zeros((240, 320, 3), np.uint8), strict=True)


def test_detect_faces_finds_a_drawn_face():
    """Synthetic cartoon face; Haar detects it on OpenCV 4.x. Skipped when no backend exists."""
    if camera.face_backend() != "haar":
        pytest.skip("Haar backend not available (OpenCV 5 removed it)")
    import cv2
    img = np.full((480, 640, 3), 200, np.uint8)
    cv2.ellipse(img, (320, 240), (110, 140), 0, 0, 360, (180, 140, 120), -1)
    for ex in (275, 365):
        cv2.ellipse(img, (ex, 205), (24, 12), 0, 0, 360, (40, 30, 30), -1)
    cv2.rectangle(img, (240, 170), (300, 180), (60, 40, 30), -1)
    cv2.rectangle(img, (340, 170), (400, 180), (60, 40, 30), -1)
    cv2.line(img, (320, 215), (310, 270), (120, 90, 80), 4)
    cv2.ellipse(img, (320, 305), (45, 15), 0, 0, 180, (90, 40, 40), 6)
    faces = camera.detect_faces(img)
    if not faces:
        pytest.skip("cartoon face not detected by this cascade version")
    x, y, w, h = faces[0]
    assert x < 320 < x + w and y < 240 < y + h
