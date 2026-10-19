from fixtures import clean_video, speech_like_audio
from studio.edit import audio


def test_measure_and_normalize(tmp_path):
    v = clean_video(tmp_path / "v.mp4", 3.0, tone_db=-30)
    before = audio.measure_loudness(v)
    assert before.integrated_lufs < -25
    after = audio.normalize_loudness(v, tmp_path / "n.mp4", target_lufs=-14, target_tp=-1.5)
    assert abs(after.integrated_lufs + 14) < 1.0
    assert after.true_peak_dbtp <= -1.0
    from studio.core.io import probe
    assert probe(tmp_path / "n.mp4").has_video     # video stream copied through


def test_cleanup_and_ducking(tmp_path):
    voice = speech_like_audio(tmp_path / "voice.wav", 4.0)
    clean = audio.clean_voice(voice, tmp_path / "clean.wav")
    assert clean.exists()
    music = clean_video(tmp_path / "m.mp4", 4.0, tone_db=-12)
    out = audio.duck_music(voice, music, tmp_path / "mix.wav")
    assert audio.measure_peak(out) < 0.5


def test_sfx_and_crossfade(tmp_path):
    a = speech_like_audio(tmp_path / "a.wav", 3.0)
    b = speech_like_audio(tmp_path / "b.wav", 3.0)
    x = audio.crossfade(a, b, tmp_path / "x.wav", 0.5)
    from studio.core.io import probe
    assert abs(probe(x).duration - 5.5) < 0.05
    s = audio.place_sfx(a, [(b, 1.0, -6)], tmp_path / "s.wav")
    assert abs(probe(s).duration - 3.0) < 0.05


def test_cleanup_filter_string():
    f = audio.cleanup_filter(denoise=0, compress=False, deess=False, presence_db=0)
    assert f == "highpass=f=80"
