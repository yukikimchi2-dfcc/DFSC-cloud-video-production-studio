import pytest

from fixtures import clean_video, make_transcript, speech_like_audio
from studio.core.io import probe
from studio.edit import speech_clean as sc
from studio.edit.transcribe import mark_fillers


@pytest.fixture(scope="module")
def wav(tmp_path_factory):
    return speech_like_audio(tmp_path_factory.mktemp("sc") / "speech.wav", 6.0)


def test_detect_silences(wav):
    sil = sc.detect_silences(wav, min_silence=0.35)
    assert len(sil) >= 3
    for a, b in sil[:3]:
        assert 0.6 <= b - a <= 0.9


def test_plan_and_render_cut_shortens_pauses(wav, tmp_path):
    plan = sc.plan_cuts(wav, max_pause=0.5, keep_pause=0.15)
    assert plan.removed and all(r[2] == "pause" for r in plan.removed)
    assert 3.5 < plan.kept_duration < 5.0
    edl = sc.plan_to_edl(plan, str(wav))
    out = sc.render_cut(edl, tmp_path / "cut.wav")
    # acrossfade overlaps shorten the result a little
    assert abs(probe(out).duration - plan.kept_duration) < 0.03 * len(plan.keep) + 0.05
    assert len(sc.detect_silences(out, min_silence=0.35)) == 0


def test_filler_ranges_removed(wav):
    t = make_transcript(str(wav))
    mark_fillers(t)
    plan = sc.plan_cuts(wav, t, max_pause=10)
    reasons = " ".join(r[2] for r in plan.removed)
    assert "filler:嗯" in reasons and "filler:然后" in reasons


def test_video_cut_keeps_sync(tmp_path):
    v = clean_video(tmp_path / "v.mp4", 3.0)
    from studio.edit.segments import EDL, EDLEvent
    edl = EDL("t", 25, [EDLEvent(0, "A", str(v), 0.0, 1.0, "", 1), EDLEvent(0, "B", str(v), 2.0, 2.8, "", 1)])
    edl.relink()
    out = sc.render_cut(edl, tmp_path / "out.mp4")
    info = probe(out)
    assert info.has_video and info.has_audio and abs(info.duration - 1.8) < 0.1


def test_snap_cut_moves_to_quiet(wav):
    from studio.core.io import read_audio
    audio = read_audio(wav, sc.SR, mono=True)[:, 0]
    t = sc.snap_cut(audio, 1.02, search=0.06)   # tone ends at 1.0 s
    assert 0.995 <= t <= 1.08


def test_verify_cut_reports_missing_words():
    a = make_transcript()
    b = make_transcript()
    b.segments[1].words = [w for w in b.segments[1].words if w.text != "困难"]
    mark_fillers(a), mark_fillers(b)
    v = sc.verify_cut(a, b)
    assert not v.ok and v.missing == ["困难"]
    assert sc.verify_cut(a, make_transcript()).ok
