"""DFSC 采访 Reel — Nelson Chin · 五告凉 GAO CHILL Herbal Tea · 第十屆參賽者.

Source: 9Oct_凉茶_0050.MP4 (Drive 1Wa3MwPiNKw12j3q6i7C5DUBeIgqH6v3X, 1728x3072 HEVC 59.94 fps, 107 s).
Style: DFSC_Interview_Reel (REFERENCE ONLY) — matched to the same-day reels DFCC_9Oct_JoshuaChin_SmartRental
and DFCC_9Oct_ChiliAng_Eggteen (see README.md next to this file for the per-element reference timecodes).

Everything that decides the cut lives in the data blocks below (RANGES / CUES / OVERLAYS), all in
SOURCE time, so the edit can be re-cut by changing numbers and re-running:

    python3 projects/dfsc-2027/edits/nelson_chin_gaochill/edit.py \
        --source workspace/sources/9Oct_凉茶_0050.MP4 --outro-ref workspace/references/chili.mp4

Stages: A) cut + punch-in A-roll with ffmpeg  B) map subtitles/graphics to output time
        C) composite graphics with the studio Timeline  D) append brand outro, loudness-normalise, QC.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from studio.brand import load_brand  # noqa: E402
from studio.core.timeline import ImageLayer, Timeline, VideoClipLayer  # noqa: E402
from studio.edit.speech_clean import frame_energy_db, snap_cut  # noqa: E402
from studio.motion import dfsc as D  # noqa: E402
from studio.render.renderer import loudnorm  # noqa: E402
from studio.versioning import reserve_output  # noqa: E402

FPS_NUM, FPS_DEN = 60000, 1001
FPS = FPS_NUM / FPS_DEN
W, H = 1080, 1920
SR = 16000

# ------------------------------------------------------------------ cut list (source seconds)
# Interviewer questions are cut from the audio and shown as small labels instead, as in the
# reference reels (JoshuaChin 0:25「拿到100千 第一步?」, 0:30「創業靠天份還是方法?」).
RANGES = [
    ("hook",   19.26, 22.95),   # 可是我沒有想到我踏上了這條不歸路，反而更累
    ("intro",   6.45, 11.70),   # 我在賣涼茶，我賣五告凉涼茶，100%天然食材，沒有加糖的
    ("why",    15.75, 22.95),   # 因為…時間比較flexible…可是我沒有想到…反而更累
    ("dream1", 28.52, 29.96),   # 一年半前
    ("dream2", 38.50, 50.90),   # 當初我們去逛市集…所以我們才看到這個商機，我們就做了我們這款涼茶
    ("money",  57.28, 61.25),   # 啟動資金的話，差不多8000塊左右
    ("before1", 67.58, 69.05, 0.02),  # 我也是在創業 (start pinned: earlier picks up the 「呢」 of 創業前呢)
    ("before2", 70.50, 72.12),  # before我做這個涼茶   (two false starts removed)
    ("before3", 75.88, 80.90),  # 我是開marketing agency的，也就是說幫人家做branding，做設計的這一些
    ("now",    83.95, 95.30),   # 對，還在做著。所以如果涼茶成功的話…part time，希望
    ("last",  101.60, 103.92),  # 投我涼茶吧，五告凉涼茶
]
PAUSE_DB, PAUSE_MIN, PAUSE_KEEP = -34.0, 0.30, 0.09   # pauses ≥0.30 s shortened to 2×0.09 s
ZOOM_IN, FOCUS = 1.14, (0.5, 0.30)                    # alternate punch-in on every jump cut

# ------------------------------------------------------------------ subtitles (Traditional; [x] = green keyword)
# (range, src_start, src_end, text). Text is what he says, corrected from the ASR:
# 步歸路→不歸路, 五高凉→五告凉 (brand writes 凉 on its logo, kept as-is); 這款 / 做著 confirmed by
# focused re-transcription of the source clips.
CUES = [
    ("hook", 19.30, 20.72, "可是我沒有想到"),
    ("hook", 20.72, 21.90, "我踏上了這條[不歸路]"),
    ("hook", 21.90, 22.90, "反而[更累]"),
    ("intro", 6.50, 7.45, "我在賣涼茶"),
    ("intro", 7.45, 9.28, "我賣[五告凉]涼茶"),
    ("intro", 9.28, 10.88, "我們是[100%天然食材]"),
    ("intro", 10.88, 11.66, "[沒有加糖]的"),
    ("why", 15.80, 17.12, "因為我個人認為"),
    ("why", 17.12, 18.28, "時間比較[flexible]"),
    ("why", 18.28, 19.30, "如果創業的話"),
    ("why", 19.30, 20.72, "可是我沒有想到"),
    ("why", 20.72, 21.90, "我踏上了這條[不歸路]"),
    ("why", 21.90, 22.90, "反而[更累]"),
    ("dream1", 28.55, 29.95, "[一年半]前"),
    ("dream2", 38.55, 40.18, "當初我們去逛[市集]"),
    ("dream2", 40.18, 42.18, "是因為我們看到市集上"),
    ("dream2", 42.18, 43.42, "所賣的東西"),
    ("dream2", 43.42, 45.20, "都是[糖分]可能比較高"),
    ("dream2", 45.20, 46.46, "然後也比較"),
    ("dream2", 46.46, 47.75, "沒有那麼[養生]的東西"),
    ("dream2", 47.75, 49.28, "所以我們才看到這個[商機]"),
    ("dream2", 49.28, 50.88, "我們就做了我們這款[涼茶]"),
    ("money", 57.30, 59.10, "啟動資金的話"),
    ("money", 59.10, 61.22, "差不多[8000塊]左右"),
    ("before1", 67.60, 69.03, "我也是在[創業]"),
    ("before2", 70.52, 72.10, "before我做這個涼茶"),
    ("before3", 75.90, 77.85, "我是開[marketing agency]的"),
    ("before3", 77.85, 79.79, "也就是說幫人家做[branding]"),
    ("before3", 79.79, 80.88, "做[設計]的這一些"),
    ("now", 83.98, 85.50, "對，還在做著"),
    ("now", 85.50, 87.30, "所以如果涼茶[成功]的話"),
    ("now", 87.30, 89.70, "我就想把涼茶變成我的[正職]"),
    ("now", 89.70, 91.60, "然後marketing agency"),
    ("now", 91.60, 94.68, "讓他自己順著去變我的[part time]"),
    ("now", 94.68, 95.28, "[希望]"),
    ("last", 101.62, 102.85, "[投我涼茶]吧"),
    ("last", 102.85, 103.90, "[五告凉]涼茶"),
]

# ------------------------------------------------------------------ graphics (source time windows)
# kinds: pill = question bar (top), small = small dark label, label = navy bar, green = green bar,
#        big = big title, name = name tag. Small labels carry the interviewer's actual question.
OVERLAYS = [
    ("hook", 19.26, 22.95, "pill", "創業還是打工？", {}),
    ("hook", 19.26, 22.95, "small", "沒想到", {"y": 262}),
    ("hook", 20.72, 22.95, "big", "不歸路", {"color": "#E53935", "role": "title", "size": 170, "y": 430}),
    ("intro", 6.45, 9.28, "name", "Nelson Chin", {"subline": "五告凉 · 第十屆參賽者", "left": "👋", "right": "🍵"}),
    ("intro", 9.28, 11.70, "small", "五告凉涼茶", {"y": 262}),
    ("intro", 9.28, 11.70, "green", "100%天然 · 沒有加糖", {"sticker": "🌿", "side": "left"}),
    ("why", 15.75, 22.95, "small", "為什麼選擇創業？", {"y": 262}),
    ("why", 15.75, 19.30, "label", "時間比較[flexible]", {"sticker": "⏰"}),
    ("why", 19.30, 22.95, "big", "反而更累", {"sticker": "😩", "size": 170, "y": 440}),
    ("dream1", 28.52, 29.96, "small", "夢想從什麼時候開始？", {"y": 262}),
    ("dream1", 28.52, 29.96, "green", "一年半前", {"sticker": "🗓", "side": "left"}),
    ("dream2", 38.50, 43.42, "small", "夢想從什麼時候開始？", {"y": 262}),
    ("dream2", 38.50, 43.42, "label", "逛[市集]", {"sticker": "🛒"}),
    ("dream2", 43.42, 47.75, "small", "市集上賣的東西", {"y": 262}),
    ("dream2", 43.42, 47.75, "label", "[糖分]比較高", {"sticker": "🍬"}),
    ("dream2", 47.75, 50.90, "green", "看到這個商機", {"sticker": "💡", "side": "left"}),
    ("money", 57.28, 61.25, "small", "第一筆啟動資金？", {"y": 262}),
    ("money", 59.10, 61.25, "big", "8000塊", {"sticker": "💰", "size": 180, "y": 440}),
    ("before1", 67.58, 72.12, "small", "剛開始創業 做什麼行業？", {"y": 262}),
    ("before1", 67.58, 72.12, "label", "我也是在[創業]", {"sticker": "💼"}),
    ("before3", 75.88, 77.85, "small", "做涼茶之前", {"y": 262}),
    ("before3", 75.88, 77.85, "label", "[Marketing Agency]", {"sticker": "💼"}),
    ("before3", 77.85, 80.90, "green", "Branding · 設計", {"sticker": "🎨", "side": "left"}),
    ("now", 83.95, 87.30, "small", "現在還在做這一行嗎？", {"y": 262}),
    ("now", 83.95, 87.30, "label", "還在做", {"sticker": "✅"}),
    ("now", 87.30, 91.60, "small", "如果涼茶成功的話", {"y": 262}),
    ("now", 87.30, 91.60, "label", "涼茶 → [正職]", {"sticker": "🎯"}),
    ("now", 91.60, 95.30, "small", "如果涼茶成功的話", {"y": 262}),
    ("now", 91.60, 95.30, "label", "Agency → [Part time]", {}),
    ("last", 101.60, 103.92, "small", "如果有人給你100千？", {"y": 262}),
    ("last", 101.60, 103.92, "big", "投我涼茶吧", {"color": "#4CC94C", "role": "title", "size": 150, "y": 440,
                                              "sticker": "🔥"}),
]
FLASH_BEFORE = ["dream1", "money", "now"]   # white flash at these section starts (ChiliAng 59.2)


# ------------------------------------------------------------------ stage A: cut list → pieces
@dataclass
class Piece:
    rng: str
    src_in: float
    src_out: float
    out_in: float = 0.0
    zoom: float = 1.0

    @property
    def dur(self) -> float:
        return self.src_out - self.src_in


def plan_pieces(audio: np.ndarray) -> list[Piece]:
    db, hop = frame_energy_db(audio, SR, 0.01)
    pieces: list[Piece] = []
    for name, a, b, *opt in RANGES:
        search = opt[0] if opt else 0.08               # optional per-range snap window
        a, b = snap_cut(audio, a, SR, search), snap_cut(audio, b, SR, 0.08)
        # shorten internal pauses
        quiet = db[int(a / hop):int(b / hop)] < PAUSE_DB
        cuts, start = [], None
        for i, q in enumerate(np.append(quiet, False)):
            if q and start is None:
                start = i
            elif not q and start is not None:
                if (i - start) * hop >= PAUSE_MIN and start > 0 and i < len(quiet):
                    s, e = a + start * hop, a + i * hop
                    cuts.append((s + PAUSE_KEEP, e - PAUSE_KEEP))
                start = None
        t = a
        for s, e in cuts:
            pieces.append(Piece(name, t, snap_cut(audio, s, SR, 0.03)))
            t = snap_cut(audio, e, SR, 0.03)
        pieces.append(Piece(name, t, b))
    out, zoom_state = 0.0, False
    for p in pieces:
        n = max(int(round(p.dur * FPS)), 1)           # whole frames keep picture and sound locked
        p.src_out = p.src_in + n / FPS
        p.out_in = out
        p.zoom = ZOOM_IN if zoom_state else 1.0
        zoom_state = not zoom_state
        out += n / FPS
    return pieces


def render_aroll(pieces: list[Piece], source: Path, work: Path) -> Path:
    parts = []
    for i, p in enumerate(pieces):
        part = work / f"piece_{i:03d}.mov"
        parts.append(part)
        if part.exists():
            continue
        z, (fx, fy) = p.zoom, FOCUS
        vf = (f"crop=iw/{z}:ih/{z}:(iw-iw/{z})*{fx}:(ih-ih/{z})*{fy},"
              f"scale={W}:{H}:flags=lanczos,fps={FPS_NUM}/{FPS_DEN},setsar=1")
        af = f"afade=t=in:d=0.012,afade=t=out:st={p.dur - 0.012:.4f}:d=0.012,aresample=48000"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{p.src_in:.4f}", "-t", f"{p.dur:.4f}",
                        "-i", str(source), "-map", "0:v:0", "-map", "0:a:0", "-vf", vf, "-af", af,
                        "-frames:v", str(int(round(p.dur * FPS))), "-c:v", "libx264", "-crf", "12",
                        "-preset", "fast", "-pix_fmt", "yuv420p", "-c:a", "pcm_s16le", str(part)], check=True)
    lst = work / "pieces.txt"
    lst.write_text("".join(f"file '{p.name}'\n" for p in parts))
    aroll = work / "aroll.mov"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
                    "-c", "copy", str(aroll)], check=True)
    return aroll


# ------------------------------------------------------------------ stage B: source → output time
def to_out(pieces: list[Piece], rng: str, t: float) -> float:
    own = [p for p in pieces if p.rng == rng]
    for p in own:
        if p.src_in <= t <= p.src_out:
            return p.out_in + (t - p.src_in)
    # inside a removed pause (or past an edge): snap to the nearest kept boundary
    best = min(own, key=lambda p: min(abs(t - p.src_in), abs(t - p.src_out)))
    return best.out_in if abs(t - best.src_in) < abs(t - best.src_out) else best.out_in + best.dur


def range_span(pieces, rng):
    own = [p for p in pieces if p.rng == rng]
    return own[0].out_in, own[-1].out_in + own[-1].dur


def build_cues(pieces):
    cues = []
    for rng, a, b, text in CUES:
        s, e = to_out(pieces, rng, a), to_out(pieces, rng, b)
        rs, re_ = range_span(pieces, rng)
        cues.append([max(s, rs), min(e, re_), text])
    cues.sort()
    for i in range(len(cues) - 1):                     # no gaps / overlaps between consecutive lines
        if cues[i + 1][0] - cues[i][1] < 0.25:
            cues[i][1] = cues[i + 1][0]
    return [tuple(c) for c in cues]


def build_overlays(pieces):
    layers = []
    for rng, a, b, kind, text, o in OVERLAYS:
        s = to_out(pieces, rng, a)
        e = to_out(pieces, rng, b)
        rs, re_ = range_span(pieces, rng)
        s, e = max(s, rs), min(e, re_)
        kw = dict(start=s, duration=e - s, z=20)
        if kind == "pill":
            layers.append(D.InterviewQuestionPill(text, **kw))
        elif kind == "small":
            layers.append(D.InterviewSmallLabel(text, y=o.get("y", 262), size=40, **kw, ))
        elif kind in ("label", "green"):
            layers.append(D.InterviewTopLabel(text, y=o.get("y", 432), size=72, sticker=o.get("sticker"),
                                              style="green" if kind == "green" else "navy",
                                              sticker_side=o.get("side", "right"), **kw))
        elif kind == "big":
            layers.append(D.InterviewBigTitle(text, y=o.get("y", 430), size=o.get("size", 170),
                                              sticker=o.get("sticker"), color=o.get("color", "#111111"),
                                              role=o.get("role", "serif_title"), **kw))
        elif kind == "name":
            layers.append(D.InterviewNameTag(text, y=330, size=110, left_sticker=o.get("left"),
                                             right_sticker=o.get("right"), subline=o.get("subline", ""), **kw))
    for rng in FLASH_BEFORE:
        rs, _ = range_span(pieces, rng)
        layers.append(D.WhiteFlash(start=max(rs - 0.07, 0), z=90))
    return layers


def srt(cues) -> str:
    def ts(t):
        ms = int(round(t * 1000))
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
    return "".join(f"{i}\n{ts(s)} --> {ts(e)}\n{t.replace('[', '').replace(']', '')}\n\n"
                   for i, (s, e, t) in enumerate(cues, 1))


# ------------------------------------------------------------------ main
def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--outro-ref", required=True, help="DFCC_9Oct_ChiliAng_Eggteen.mp4 (brand outro 60.70–end)")
    ap.add_argument("--outro-in", type=float, default=60.70)
    ap.add_argument("--work", default=str(ROOT / "workspace/edits/nelson_chin_gaochill"))
    ap.add_argument("--out-dir", default=str(ROOT / "renders/dfsc-2027"))
    ap.add_argument("--preview", action="store_true", help="720p fast render")
    ap.add_argument("--plan-only", action="store_true")
    a = ap.parse_args(argv)
    work = Path(a.work)
    work.mkdir(parents=True, exist_ok=True)
    source = Path(a.source)

    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(source), "-map", "0:a:0", "-ac", "1", "-ar", str(SR),
                          "-f", "f32le", "-"], capture_output=True, check=True).stdout
    audio = np.frombuffer(raw, np.float32).copy()       # first audio stream = handheld mic
    pieces = plan_pieces(audio)
    cues = build_cues(pieces)
    total = pieces[-1].out_in + pieces[-1].dur
    plan = {"pieces": [p.__dict__ | {"dur": p.dur} for p in pieces], "aroll_seconds": total,
            "cues": cues}
    (work / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=1))
    (work / "subtitles.srt").write_text(srt(cues), encoding="utf-8")
    print(f"pieces={len(pieces)} aroll={total:.2f}s cues={len(cues)}")
    if a.plan_only:
        return

    aroll = render_aroll(pieces, source, work)

    brand = load_brand("dfsc-2027")
    tl = Timeline(W, H, FPS, duration=total, brand=brand)
    tl.add(VideoClipLayer(aroll, duration=total, z=-100))
    tl.add(ImageLayer(ROOT / "projects/dfsc-2027/brand/logos/dreamfactory_watermark.png", x=34, y=60,
                      height=104, duration=total, opacity=0.92, z=40))
    tl.add(*build_overlays(pieces))
    tl.add(D.InterviewSubtitle(cues, y=1400, size=66, z=30))
    gfx = work / ("graphics_preview.mp4" if a.preview else "graphics.mp4")
    pw, ph = (720, 1280) if a.preview else (W, H)
    tl.render(gfx, width=pw, height=ph, crf=14, preset="fast" if a.preview else "medium",
              progress=lambda d, n: print(f"\rframes {d}/{n}", end="", flush=True) if d % 120 == 0 or d == n else None)
    print()

    # stage D: brand outro (identical in JoshuaChin 0:42 / ChiliAng 1:00) + loudness
    outro = work / f"outro_{pw}.mov"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{a.outro_in}", "-i", a.outro_ref,
                    "-vf", f"scale={pw}:{ph}:flags=lanczos,fps={FPS_NUM}/{FPS_DEN},setsar=1",
                    "-af", "aresample=48000,afade=t=in:d=0.08", "-c:v", "libx264", "-crf", "12", "-preset", "fast",
                    "-pix_fmt", "yuv420p", "-c:a", "pcm_s16le", "-ac", "1", str(outro)], check=True)
    mode = "preview" if a.preview else "final"
    out = reserve_output(a.out_dir, "dfsc2027_nelson_chin_gaochill", mode)
    xf = 0.12   # reference cross-dissolves into the outro over ≈0.12 s (ChiliAng 60.58–60.70)
    fc = (f"[0:v]setpts=PTS-STARTPTS[v0];[2:v]setpts=PTS-STARTPTS[v1];"
          f"[v0][v1]xfade=transition=fade:duration={xf}:offset={total - xf:.4f},format=yuv420p[v];"
          f"[1:a]highpass=f=80,afftdn=nr=10:nf=-40,aresample=48000,aformat=channel_layouts=mono,"
          f"loudnorm=I=-14:TP=-2:LRA=9[sp];"
          f"[2:a]aformat=channel_layouts=mono,loudnorm=I=-15:TP=-2:LRA=9[ou];"
          f"[sp][ou]acrossfade=d={xf}[mix];"
          f"[mix]aresample=48000[a]")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(gfx), "-i", str(aroll), "-i", str(outro),
                    "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
                    "-c:v", "libx264", "-preset", "veryfast" if a.preview else "slow",
                    "-crf", "26" if a.preview else "17", "-profile:v", "high", "-pix_fmt", "yuv420p",
                    "-r", f"{FPS_NUM}/{FPS_DEN}", "-c:a", "aac", "-b:a", "128k" if a.preview else "256k",
                    "-ac", "2", "-movflags", "+faststart", str(premaster := work / f"premaster_{mode}.mp4")],
                   check=True)
    # final loudness: two-pass linear EBU R128 to the project target (single-pass undershoots ~1 LU)
    loudnorm(premaster, out, -14.0, -1.5, bitrate="128k" if a.preview else "256k")
    (work / "last_output.txt").write_text(str(out))
    print(out)


if __name__ == "__main__":
    main()
