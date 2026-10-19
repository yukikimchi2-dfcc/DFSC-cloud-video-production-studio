import os

import pytest

from fixtures import make_transcript
from studio.edit import transcribe as tr


def test_json_roundtrip_and_srt(tmp_path):
    t = make_transcript()
    p = t.save(tmp_path / "t.json")
    back = tr.Transcript.load(p)
    assert back.to_dict() == t.to_dict()
    srt = back.to_srt()
    assert srt.startswith("1\n00:00:00,000 --> ")
    assert srt.count("-->") == len(t.segments)


def test_filler_detection():
    t = make_transcript()
    n = tr.mark_fillers(t)
    fillers = [w.text for w in t.words if w.is_filler]
    assert "嗯" in fillers and "然后" in fillers
    assert "导师" not in fillers
    assert n == len(fillers)
    # custom list replaces default
    tr.mark_fillers(t, ["导师"])
    assert [w.text for w in t.words if w.is_filler] == ["导师"]


def test_traditional_conversion():
    out = tr.to_traditional("为什么创业这么难")
    assert out in ("為什麼創業這麼難", "为什么创业这么难")  # identity only if OpenCC missing
    pytest.importorskip("opencc")
    assert out == "為什麼創業這麼難"


def test_heuristic_speakers_without_audio():
    t = make_transcript()
    t.segments[3].start += 2.0   # long pause before segment 3
    n = tr.assign_speakers(t, None, min_pause=1.2)
    assert n == 2
    assert t.segments[0].speaker == "S0" and t.segments[3].speaker == "S1"
    assert all(w.speaker == t.segments[3].speaker for w in t.segments[3].words)


@pytest.mark.network
def test_whisper_transcription_or_clear_error(tmp_path):
    from fixtures import speech_like_audio
    wav = speech_like_audio(tmp_path / "a.wav", 2.0)
    try:
        result = tr.transcribe(wav)
    except tr.ModelUnavailableError as e:
        assert "STUDIO_WHISPER_MODEL_DIR" in str(e)
        pytest.skip(f"Whisper weights unavailable (huggingface.co blocked or no local model): {str(e).splitlines()[0]}")
    assert isinstance(result, tr.Transcript)
