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


# ---- Groq (free hosted Whisper) backend -------------------------------------------------
def test_backend_auto_prefers_groq_only_with_key(monkeypatch):
    from studio.edit.transcribe import _backend
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert _backend({"transcription": {"backend": "auto"}}) == "local"
    monkeypatch.setenv("GROQ_API_KEY", "x")
    assert _backend({"transcription": {"backend": "auto"}}) == "groq"
    assert _backend({"transcription": {"backend": "local"}}) == "local"


def test_parse_groq_response_offsets_and_assigns_words():
    from studio.edit.transcribe import parse_groq_response, to_traditional
    data = {"text": "创业不是一个人", "segments": [{"start": 0.0, "end": 1.0, "text": "创业", "avg_logprob": -0.1},
                                             {"start": 1.0, "end": 2.0, "text": "不是一个人", "avg_logprob": -0.2}],
            "words": [{"word": "创业", "start": 0.1, "end": 0.8}, {"word": "不是", "start": 1.1, "end": 1.4},
                      {"word": "一个人", "start": 1.4, "end": 1.9}]}
    segs = parse_groq_response(data, offset=600.0, conv=to_traditional)
    assert [s.start for s in segs] == [600.0, 601.0]
    assert [w.text for w in segs[1].words] == ["不是", "一個人"]      # Traditional conversion applied
    assert segs[0].words[0].start == 600.1


def test_groq_backend_end_to_end_with_mocked_api(monkeypatch, tmp_path):
    import requests

    from studio.edit import transcribe as T
    from studio.render.demo import make_test_tone
    audio = make_test_tone(tmp_path / "a.wav", duration=3.0)
    calls = []

    class Resp:
        status_code = 200
        headers = {}

        def json(self):
            return {"text": "大家好", "segments": [{"start": 0.0, "end": 2.0, "text": "大家好"}],
                    "words": [{"word": "大家", "start": 0.2, "end": 0.9}, {"word": "好", "start": 0.9, "end": 1.4}]}

    def fake_post(url, headers, files, data, timeout):
        calls.append((url, dict(data), headers["Authorization"]))
        return Resp()

    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setattr(requests, "post", fake_post)
    tr = T.transcribe(audio, {"transcription": {"backend": "auto", "language": "zh"}}, speakers=False)
    assert tr.model == "groq:whisper-large-v3-turbo"
    assert [w.text for w in tr.words] == ["大家", "好"]
    url, data, auth = calls[0]
    assert url == T.GROQ_URL and data["model"] == "whisper-large-v3-turbo" and auth == "Bearer test-key"
