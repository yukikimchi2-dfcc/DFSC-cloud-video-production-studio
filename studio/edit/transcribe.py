"""Transcription: Whisper (faster-whisper) word-level transcripts, filler detection, speaker turns.

The data model (Word / Segment / Transcript) is independent of the ASR backend so the rest of
the pipeline (subtitles, segment selection, speech cleaning) can be tested with hand-made data.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from ..config import get, load_config
from ..core.io import read_audio

DEFAULT_FILLERS = ["嗯", "呃", "啊", "欸", "誒", "哦", "喔", "那個", "这个", "這個", "就是", "然後", "然后",
                   "對", "对", "對對", "对对", "其實", "其实", "基本上", "怎麼說", "怎么说"]


class ModelUnavailableError(RuntimeError):
    pass


@dataclass
class Word:
    start: float
    end: float
    text: str
    confidence: float = 1.0
    speaker: str | None = None
    is_filler: bool = False


@dataclass
class Segment:
    start: float
    end: float
    text: str
    words: list[Word] = field(default_factory=list)
    speaker: str | None = None
    confidence: float = 1.0


@dataclass
class Transcript:
    source: str
    language: str
    segments: list[Segment] = field(default_factory=list)
    model: str | None = None

    @property
    def words(self) -> list[Word]:
        return [w for s in self.segments for w in s.words]

    @property
    def text(self) -> str:
        return "".join(s.text for s in self.segments)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Transcript":
        segs = [Segment(**{**s, "words": [Word(**w) for w in s.get("words", [])]}) for s in d.get("segments", [])]
        return cls(source=d["source"], language=d.get("language", "zh"), segments=segs, model=d.get("model"))

    def save(self, path: str | Path) -> Path:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=1), encoding="utf-8")
        return Path(path)

    @classmethod
    def load(cls, path: str | Path) -> "Transcript":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    def to_srt(self) -> str:
        return "\n".join(f"{i}\n{srt_time(s.start)} --> {srt_time(s.end)}\n{s.text}\n"
                         for i, s in enumerate(self.segments, 1))


def srt_time(t: float) -> str:
    ms = int(round(max(t, 0) * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


# ---------------------------------------------------------------- script conversion

def to_traditional(text: str) -> str:
    """Simplified -> Traditional (Taiwan phrasing when OpenCC is available); identity fallback."""
    conv = _opencc()
    return conv.convert(text) if conv else text


_OPENCC = None


def _opencc():
    global _OPENCC
    if _OPENCC is None:
        try:
            from opencc import OpenCC
            try:
                _OPENCC = OpenCC("s2twp")
            except Exception:
                _OPENCC = OpenCC("s2t")
        except ImportError:
            _OPENCC = False
    return _OPENCC or None


# ---------------------------------------------------------------- fillers & speakers

def mark_fillers(transcript: Transcript, fillers: list[str] | None = None) -> int:
    """Flag words that are pure filler tokens (after stripping punctuation). Returns count."""
    fillers = set(fillers or DEFAULT_FILLERS)
    n = 0
    for w in transcript.words:
        token = w.text.strip().strip("，。、！？,.!?…~ ")
        w.is_filler = bool(token) and (token in fillers or (len(set(token)) == 1 and token[0] in fillers))
        n += w.is_filler
    return n


def assign_speakers(transcript: Transcript, audio_path: str | Path | None = None,
                    min_pause: float = 1.2, energy_jump_db: float = 6.0) -> int:
    """HEURISTIC speaker turns: a new speaker label starts after a long pause combined with a
    loudness jump between neighbouring segments. Not real diarization — swap in pyannote by
    replacing this function (same contract: set Segment.speaker / Word.speaker). Returns #speakers."""
    segs = transcript.segments
    if not segs:
        return 0
    levels = [0.0] * len(segs)
    if audio_path:
        sr = 16000
        audio = read_audio(audio_path, sr, mono=True)[:, 0]
        for i, s in enumerate(segs):
            chunk = audio[int(s.start * sr):int(s.end * sr)]
            levels[i] = 20 * np.log10(np.sqrt(np.mean(chunk ** 2)) + 1e-9) if len(chunk) else -90
    label, speakers = 0, {0}
    for i, s in enumerate(segs):
        if i > 0:
            pause = s.start - segs[i - 1].end
            jump = abs(levels[i] - levels[i - 1])
            if pause >= min_pause and (not audio_path or jump >= energy_jump_db):
                label = (label + 1) % 2   # alternate between two speakers (interviewer / interviewee)
                speakers.add(label)
        s.speaker = f"S{label}"
        for w in s.words:
            w.speaker = s.speaker
    return len(speakers)


# ---------------------------------------------------------------- ASR

def _load_model(cfg: dict):
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise ModelUnavailableError("faster-whisper is not installed: pip install faster-whisper") from e
    model_name = os.environ.get("STUDIO_WHISPER_MODEL_DIR") or get(cfg, "transcription.model", "large-v3-turbo")
    device = get(cfg, "transcription.device", "auto")
    compute = get(cfg, "transcription.compute_type", "auto")
    if device == "auto":
        device = "cuda" if _has_cuda() else "cpu"
    if compute == "auto":
        compute = "float16" if device == "cuda" else "int8"
    try:
        return WhisperModel(model_name, device=device, compute_type=compute), model_name
    except Exception as e:  # network blocked, missing weights, bad path ...
        raise ModelUnavailableError(
            f"Could not load Whisper model '{model_name}': {e}\n"
            "Fix: allow huggingface.co in the environment's network policy so the weights can download, "
            "or download 'Systran/faster-whisper-large-v3-turbo' (or mobiuslabsgmbh/faster-whisper-large-v3-turbo) "
            "elsewhere and point STUDIO_WHISPER_MODEL_DIR at the folder."
        ) from e


def _has_cuda() -> bool:
    try:
        import ctranslate2
        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


PROMPT_TC = "以下是繁體中文的訪談內容。"


def _backend(cfg: dict) -> str:
    backend = get(cfg, "transcription.backend", "auto")
    if backend == "auto":
        return "groq" if os.environ.get("GROQ_API_KEY") else "local"
    return backend


def _transcribe_local(path, cfg, lang, traditional, conv) -> tuple[list[Segment], str, str]:
    model, model_name = _load_model(cfg)
    raw_segments, info = model.transcribe(str(path), language=lang, word_timestamps=True, vad_filter=True,
                                          initial_prompt=PROMPT_TC if traditional else None)
    segs = []
    for rs in raw_segments:
        words = [Word(w.start, w.end, conv(w.word), float(w.probability)) for w in (rs.words or [])]
        segs.append(Segment(rs.start, rs.end, conv(rs.text.strip()), words,
                            confidence=float(np.exp(rs.avg_logprob)) if rs.avg_logprob is not None else 1.0))
    return segs, info.language or lang, str(model_name)


# Groq hosts the same Whisper large-v3-turbo model behind an OpenAI-compatible API with a free
# tier (no GPU needed here). Uploads are capped at 25 MB, so audio is sent as ~10-minute Opus
# chunks cut at silences; timestamps are shifted back by each chunk's offset.
GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"


def _chunk_bounds(path, total: float, target: float = 600.0, search: float = 30.0) -> list[tuple[float, float]]:
    if total <= target + search:
        return [(0.0, total)]
    from .speech_clean import detect_silences
    mids = [(s + e) / 2 for s, e in detect_silences(path, min_silence=0.3)]
    bounds, start = [], 0.0
    while total - start > target + search:
        mark = start + target
        near = [m for m in mids if abs(m - mark) <= search]
        cut = min(near, key=lambda m: abs(m - mark)) if near else mark
        bounds.append((start, cut))
        start = cut
    bounds.append((start, total))
    return bounds


def parse_groq_response(data: dict, offset: float, conv) -> list[Segment]:
    """verbose_json (segments + words) -> Segments with absolute times; words are assigned by time."""
    words = [Word(w["start"] + offset, w["end"] + offset, conv(w["word"])) for w in data.get("words", [])]
    segs = []
    for s in data.get("segments", []):
        start, end = s["start"] + offset, s["end"] + offset
        seg_words = [w for w in words if start - 0.05 <= (w.start + w.end) / 2 < end + 0.05]
        lp = s.get("avg_logprob")
        segs.append(Segment(start, end, conv(s["text"].strip()), seg_words,
                            confidence=float(np.exp(lp)) if lp is not None else 1.0))
    if not segs and words:
        segs = [Segment(words[0].start, words[-1].end, conv(data.get("text", "")).strip(), words)]
    return segs


def _transcribe_groq(path, cfg, lang, traditional, conv) -> tuple[list[Segment], str, str]:
    import tempfile

    import requests

    from ..core.io import probe, run_ffmpeg
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        raise ModelUnavailableError("transcription.backend is 'groq' but GROQ_API_KEY is not set "
                                    "(free key: https://console.groq.com/keys)")
    model = get(cfg, "transcription.groq_model", "whisper-large-v3-turbo")
    segs: list[Segment] = []
    with tempfile.TemporaryDirectory(prefix="studio-groq-") as tmp:
        for i, (c0, c1) in enumerate(_chunk_bounds(path, probe(path).duration)):
            chunk = Path(tmp) / f"chunk{i:03d}.ogg"
            run_ffmpeg(["-ss", f"{c0:.3f}", "-t", f"{c1 - c0:.3f}", "-i", str(path), "-vn", "-ac", "1",
                        "-ar", "16000", "-c:a", "libopus", "-b:a", "48k", str(chunk)])
            for attempt in range(5):
                with open(chunk, "rb") as f:
                    r = requests.post(GROQ_URL, headers={"Authorization": f"Bearer {key}"}, timeout=300,
                                      files={"file": (chunk.name, f, "audio/ogg")},
                                      data=[("model", model), ("language", lang), ("response_format", "verbose_json"),
                                            ("timestamp_granularities[]", "word"),
                                            ("timestamp_granularities[]", "segment"),
                                            ("prompt", PROMPT_TC if traditional else "")])
                if r.status_code == 429 or r.status_code >= 500:  # free-tier rate limit / transient
                    time.sleep(float(r.headers.get("retry-after", 2 ** (attempt + 1))))
                    continue
                if r.status_code != 200:
                    raise ModelUnavailableError(f"Groq transcription failed ({r.status_code}): {r.text[:300]}")
                segs += parse_groq_response(r.json(), c0, conv)
                break
            else:
                raise ModelUnavailableError("Groq rate limit persisted after 5 retries; try later or use backend 'local'")
    return segs, lang, f"groq:{model}"


def transcribe(path: str | Path, cfg: dict | None = None, traditional: bool = True,
               fillers: list[str] | None = None, speakers: bool = True, backend: str | None = None) -> Transcript:
    """Word-timestamped transcript of `path` (any audio/video ffmpeg can read).

    backend: "local" (faster-whisper on this machine), "groq" (free hosted Whisper API, needs
    GROQ_API_KEY) or "auto" (groq when a key is set, else local). Default from config.
    """
    cfg = cfg or load_config()
    lang = get(cfg, "transcription.language", "zh")
    conv = to_traditional if traditional else (lambda s: s)
    run = _transcribe_groq if (backend or _backend(cfg)) == "groq" else _transcribe_local
    segs, language, model_name = run(path, cfg, lang, traditional, conv)
    tr = Transcript(str(path), language, segs, model=model_name)
    mark_fillers(tr, fillers or get(cfg, "transcription.fillers"))
    if speakers:
        assign_speakers(tr, path)
    return tr
