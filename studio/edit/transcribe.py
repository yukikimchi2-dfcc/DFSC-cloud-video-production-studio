"""Transcription: Whisper (faster-whisper) word-level transcripts, filler detection, speaker turns.

The data model (Word / Segment / Transcript) is independent of the ASR backend so the rest of
the pipeline (subtitles, segment selection, speech cleaning) can be tested with hand-made data.
"""
from __future__ import annotations

import json
import os
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


def transcribe(path: str | Path, cfg: dict | None = None, traditional: bool = True,
               fillers: list[str] | None = None, speakers: bool = True) -> Transcript:
    """Word-timestamped transcript of `path` (any audio/video ffmpeg can read)."""
    cfg = cfg or load_config()
    model, model_name = _load_model(cfg)
    lang = get(cfg, "transcription.language", "zh")
    raw_segments, info = model.transcribe(str(path), language=lang, word_timestamps=True, vad_filter=True,
                                          initial_prompt="以下是繁體中文的訪談內容。" if traditional else None)
    conv = to_traditional if traditional else (lambda s: s)
    segs = []
    for rs in raw_segments:
        words = [Word(w.start, w.end, conv(w.word), float(w.probability)) for w in (rs.words or [])]
        segs.append(Segment(rs.start, rs.end, conv(rs.text.strip()), words,
                            confidence=float(np.exp(rs.avg_logprob)) if rs.avg_logprob is not None else 1.0))
    tr = Transcript(str(path), info.language or lang, segs, model=str(model_name))
    mark_fillers(tr, fillers or get(cfg, "transcription.fillers"))
    if speakers:
        assign_speakers(tr, path)
    return tr
