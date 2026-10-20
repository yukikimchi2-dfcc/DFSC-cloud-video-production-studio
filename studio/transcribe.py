"""Whisper large-v3 transcription with word timestamps (faster-whisper, CPU int8).

VAD is required: without it Whisper hallucinates on the crew chatter before the
interview starts. Word times are refined afterwards by align.py.

usage: python transcribe.py <model> <audio16k.wav> <out.json>
"""
import json
import sys
import wave

import numpy as np
from faster_whisper import WhisperModel


def main(model_name, wav_path, out_path):
    wf = wave.open(wav_path)
    audio = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    model = WhisperModel(model_name, device="cpu", compute_type="int8", cpu_threads=4)
    segs, info = model.transcribe(audio, language="zh", word_timestamps=True, vad_filter=True,
                                  condition_on_previous_text=False,
                                  vad_parameters=dict(min_silence_duration_ms=500),
                                  initial_prompt="洪记糖水。", beam_size=5)
    res = {"language": info.language, "segments": []}
    for s in segs:
        res["segments"].append({"start": s.start, "end": s.end, "text": s.text,
                                "words": [{"s": w.start, "e": w.end, "w": w.word, "p": w.probability}
                                          for w in s.words]})
        print(f"[{s.start:7.2f}-{s.end:7.2f}] {s.text}", flush=True)
    json.dump(res, open(out_path, "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main(*sys.argv[1:4])
