"""Synthetic test media generated with ffmpeg (no real footage needed). Clearly marked TEST content."""
from __future__ import annotations

import subprocess
from pathlib import Path

from studio.edit.transcribe import Segment, Transcript, Word

FONT = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
SIZE = "320x240"


def ff(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True)


def _enc(out: Path) -> list[str]:
    return ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", str(out)]


def clean_video(out: Path, dur: float = 3.0, fps: int = 25, size: str = SIZE, tone_db: float = -18.0) -> Path:
    ff("-f", "lavfi", "-i", f"testsrc2=size={size}:rate={fps}:duration={dur}",
       "-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=48000:duration={dur}",
       "-af", f"volume={tone_db + 18}dB", "-shortest", *_enc(out))   # lavfi sine peaks at -18 dBFS
    return out


def video_with_black(out: Path, fps: int = 25) -> Path:
    ff("-f", "lavfi", "-i", f"testsrc2=size={SIZE}:rate={fps}:duration=1",
       "-f", "lavfi", "-i", f"color=c=black:size={SIZE}:rate={fps}:duration=1",
       "-f", "lavfi", "-i", f"testsrc2=size={SIZE}:rate={fps}:duration=1",
       "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=3",
       "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]", "-map", "[v]", "-map", "3:a", *_enc(out))
    return out


def video_with_freeze(out: Path, fps: int = 25) -> Path:
    ff("-f", "lavfi", "-i", f"testsrc2=size={SIZE}:rate={fps}:duration=1.5",
       "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=3",
       "-vf", "tpad=stop_mode=clone:stop_duration=1.5", "-map", "0:v", "-map", "1:a", *_enc(out))
    return out


def clipping_video(out: Path) -> Path:
    ff("-f", "lavfi", "-i", f"testsrc2=size={SIZE}:rate=25:duration=2",
       "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=2",
       "-af", "volume=26dB", "-shortest", *_enc(out))
    return out


def speech_like_audio(out: Path, dur: float = 6.0) -> Path:
    """1.0 s tone bursts separated by 0.8 s silences (pause-detection target)."""
    ff("-f", "lavfi", "-i",
       f"aevalsrc='0.3*sin(2*PI*220*t)*lt(mod(t,1.8),1.0)':s=16000:d={dur}", "-c:a", "pcm_s16le", str(out))
    return out


def multi_shot_video(out: Path, fps: int = 25) -> Path:
    """Three visually distinct 2 s shots + subtitle-like text at the bottom + a 120 BPM click track."""
    text = f"drawtext=fontfile={FONT}:text='測試字幕 TEST':fontsize=22:fontcolor=white:borderw=2:x=(w-tw)/2:y=h-50"
    ff("-f", "lavfi", "-i", f"testsrc2=size={SIZE}:rate={fps}:duration=2",
       "-f", "lavfi", "-i", f"smptebars=size={SIZE}:rate={fps}:duration=2",
       "-f", "lavfi", "-i", f"mandelbrot=size={SIZE}:rate={fps},trim=duration=2",
       "-f", "lavfi", "-i", "aevalsrc='0.6*sin(2*PI*1000*t)*exp(-40*mod(t,0.5))':s=48000:d=6",
       "-filter_complex", f"[0:v][1:v][2:v]concat=n=3:v=1:a=0,{text}[v]", "-map", "[v]", "-map", "3:a", *_enc(out))
    return out


def landscape_video(out: Path, dur: float = 2.0) -> Path:
    ff("-f", "lavfi", "-i", f"testsrc2=size=640x360:rate=25:duration={dur}",
       "-f", "lavfi", "-i", f"sine=frequency=330:sample_rate=48000:duration={dur}", "-shortest", *_enc(out))
    return out


def make_transcript(source: str = "test.wav") -> Transcript:
    """Hand-made interview transcript (zh, simplified to exercise s2t conversion)."""
    def seg(start, items):
        words, t = [], start
        for text, d in items:
            words.append(Word(t, t + d, text))
            t += d
        return Segment(start, t, "".join(w.text for w in words), words)
    return Transcript(source, "zh", [
        seg(0.0, [("嗯", 0.3), ("你", 0.2), ("知道", 0.3), ("为什么", 0.4), ("创业", 0.4), ("这么", 0.3), ("难", 0.3), ("？", 0.05)]),
        seg(2.6, [("那时候", 0.4), ("我们", 0.3), ("遇到", 0.3), ("很多", 0.3), ("困难", 0.4), ("和", 0.1), ("问题", 0.4), ("。", 0.05)]),
        seg(5.2, [("然后", 0.3), ("导师", 0.4), ("帮助", 0.4), ("我们", 0.3), ("解决", 0.4), ("了", 0.1), ("方法", 0.3), ("。", 0.05)]),
        seg(8.0, [("我们", 0.3), ("成立", 0.3), ("三", 0.2), ("年", 0.2), ("营收", 0.4), ("成长", 0.4), ("百分之五十", 0.8), ("。", 0.05)]),
        seg(11.0, [("现在", 0.3), ("就", 0.2), ("报名", 0.4), ("加入", 0.4), ("我们", 0.3), ("吧", 0.2), ("！", 0.05)]),
    ])
