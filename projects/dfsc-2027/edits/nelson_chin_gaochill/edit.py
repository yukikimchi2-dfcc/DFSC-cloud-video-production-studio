"""DFSC 采访 Reel — Nelson Chin · 五告凉 GAO CHILL Herbal Tea · 第十屆參賽者.

Source: 9Oct_凉茶_0050.MP4 (Drive 1Wa3MwPiNKw12j3q6i7C5DUBeIgqH6v3X, 1728x3072 HEVC 59.94 fps, 107 s).
Style: DFSC_Interview_Reel (REFERENCE ONLY) — matched to the same-day reels DFCC_9Oct_JoshuaChin_SmartRental
and DFCC_9Oct_ChiliAng_Eggteen (see README.md next to this file for the per-element reference timecodes).
v005 additions requested by the user: filler / pause removal, faster pace, motion effects, keyword sound
effects and a background music bed (original, synthesised — studio/edit/sfx.py).

Everything that decides the cut lives in the data blocks below (RANGES / FILLER_CUTS / CUES / OVERLAYS),
all in SOURCE time, so the edit can be re-cut by changing numbers and re-running:

    python3 projects/dfsc-2027/edits/nelson_chin_gaochill/edit.py \
        --source workspace/sources/9Oct_凉茶_0050.MP4 --outro-ref workspace/references/chili.mp4

Stages: A) cut + punch-in + speed-up A-roll with ffmpeg  B) map subtitles/graphics/SFX to output time
        C) composite graphics + camera motion with the studio Timeline
        D) mix voice + music bed + SFX, append brand outro, loudness-normalise.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.ndimage import median_filter

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from studio.brand import load_brand  # noqa: E402
from studio.core.timeline import ImageLayer, Layer, Timeline, VideoClipLayer  # noqa: E402
from studio.edit import sfx as SFX  # noqa: E402
from studio.edit.speech_clean import frame_energy_db, snap_cut  # noqa: E402
from studio.motion import dfsc as D  # noqa: E402
from studio.motion.camera import CameraShake, SlowPushIn, ZoomPunch  # noqa: E402
from studio.render.renderer import loudnorm  # noqa: E402
from studio.versioning import reserve_output  # noqa: E402

FPS_NUM, FPS_DEN = 60000, 1001
FPS = FPS_NUM / FPS_DEN
W, H = 1080, 1920
SR = 16000

# ------------------------------------------------------------------ cut list (source seconds)
# Interviewer questions are cut from the audio and shown as small labels instead, as in the
# reference reels (JoshuaChin 0:25「拿到100千 第一步?」, 0:30「創業靠天份還是方法?」).
# Optional 4th value = snap window for the start (pinned starts were checked by re-transcribing the cut).
RANGES = [
    ("hook",   19.64, 22.95, 0.02),   # 可是我沒有想到我踏上了這條不歸路，反而更累 (drops the 「話」 tail before it)
    ("intro",   6.45, 11.70),         # 我在賣涼茶，我賣五告凉涼茶，100%天然食材，沒有加糖的
    ("why",    15.75, 22.95),         # 因為…時間比較flexible…可是我沒有想到…反而更累
    ("dream1", 28.76, 29.96, 0.02),   # 一年半前 (starts after 「嗯」)
    ("dream2", 38.50, 50.90),         # 當初我們去逛市集…所以我們才看到這個商機，我們就做了我們這款涼茶
    ("money",  57.80, 61.25, 0.02),   # 啟動資金的話，差不多8000塊左右 (starts after a stray 「啥」)
    ("before1", 67.58, 69.05, 0.02),  # 我也是在創業 (start pinned: earlier picks up the 「呢」 of 創業前呢)
    ("before2", 70.58, 72.12, 0.02),  # before我做這個涼茶   (two false starts removed)
    ("before3", 75.88, 80.90),        # 我是開marketing agency的，也就是說幫人家做branding，做設計的這一些
    ("now",    84.30, 95.30, 0.02),   # 對，還在做著。所以如果涼茶成功的話…part time，希望
    ("last",  101.70, 103.92, 0.02),  # 投我涼茶吧，五告凉涼茶 (starts after 「那個」)
]
# Fillers inside kept ranges, each removal verified by re-transcribing the joined audio.
FILLER_CUTS = [
    (7.40, 7.78),     # 我在賣涼茶，「啊」，我賣…
    (93.86, 94.30),   # part——time: held breath inside the phrase
]
PAUSE_DB, PAUSE_MIN, PAUSE_KEEP = -32.0, 0.22, 0.07   # pauses ≥0.22 s shortened to 2×0.07 s
EDGE_KEEP_IN, EDGE_KEEP_OUT = 0.05, 0.10              # silence kept at the head / tail of each range
SPEED = 1.15                                          # pitch-preserving speed-up of the whole A-roll
ZOOM_IN, FOCUS = 1.14, (0.5, 0.30)                    # alternate punch-in on range / filler jump cuts
PUSH_IN = 0.035                                       # slow push-in over every shot

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
# Range "a>b" lets one graphic run across consecutive ranges. Options: sfx = keyword sound effect
# (default by kind, None = silent), punch = camera punch-in while a big title is up, shake = impact shake.
OVERLAYS = [
    ("hook", 19.64, 22.95, "pill", "創業還是打工？", {}),
    ("hook", 19.64, 22.95, "small", "沒想到", {"y": 262}),
    ("hook", 20.72, 22.95, "big", "不歸路", {"color": "#E53935", "role": "title", "size": 170, "y": 430,
                                          "sfx": "impact", "punch": 0.08, "shake": True}),
    ("intro", 6.45, 9.28, "name", "Nelson Chin", {"subline": "五告凉 · 第十屆參賽者", "left": "👋", "right": "🍵"}),
    ("intro", 9.28, 11.70, "small", "五告凉涼茶", {"y": 262}),
    ("intro", 9.28, 11.70, "green", "100%天然 · 沒有加糖", {"sticker": "🌿", "side": "left"}),
    ("why", 15.75, 22.95, "small", "為什麼選擇創業？", {"y": 262}),
    ("why", 15.75, 19.30, "label", "時間比較[flexible]", {"sticker": "⏰"}),
    ("why", 19.30, 22.95, "big", "反而更累", {"sticker": "😩", "size": 170, "y": 440, "sfx": "whoosh", "punch": 0.07}),
    ("dream1", 28.76, 29.96, "small", "夢想從什麼時候開始？", {"y": 262}),
    ("dream1", 28.76, 29.96, "green", "一年半前", {"sticker": "🗓", "side": "left"}),
    ("dream2", 38.50, 43.42, "small", "夢想從什麼時候開始？", {"y": 262}),
    ("dream2", 38.50, 43.42, "label", "逛[市集]", {"sticker": "🛒"}),
    ("dream2", 43.42, 47.75, "small", "市集上賣的東西", {"y": 262}),
    ("dream2", 43.42, 47.75, "label", "[糖分]比較高", {"sticker": "🍬"}),
    ("dream2", 47.75, 50.90, "green", "看到這個商機", {"sticker": "💡", "side": "left", "sfx": "ding"}),
    ("money", 57.80, 61.25, "small", "第一筆啟動資金？", {"y": 262}),
    ("money", 59.10, 61.25, "big", "8000塊", {"sticker": "💰", "size": 180, "y": 440, "sfx": "ding", "punch": 0.07}),
    ("before1>before2", 67.58, 72.12, "small", "剛開始創業 做什麼行業？", {"y": 262}),
    ("before1>before2", 67.58, 72.12, "label", "我也是在[創業]", {"sticker": "💼"}),
    ("before3", 75.88, 77.85, "small", "做涼茶之前", {"y": 262}),
    ("before3", 75.88, 77.85, "label", "[Marketing Agency]", {"sticker": "💼"}),
    ("before3", 77.85, 80.90, "green", "Branding · 設計", {"sticker": "🎨", "side": "left"}),
    ("now", 84.30, 87.30, "small", "現在還在做這一行嗎？", {"y": 262}),
    ("now", 84.30, 87.30, "label", "還在做", {"sticker": "✅"}),
    ("now", 87.30, 91.60, "small", "如果涼茶成功的話", {"y": 262}),
    ("now", 87.30, 91.60, "label", "涼茶 → [正職]", {"sticker": "🎯"}),
    ("now", 91.60, 95.30, "small", "如果涼茶成功的話", {"y": 262}),
    ("now", 91.60, 95.30, "label", "Agency → [Part time]", {}),
    ("last", 101.70, 103.92, "small", "如果有人給你100千？", {"y": 262}),
    ("last", 101.70, 103.92, "big", "投我涼茶吧", {"color": "#4CC94C", "role": "title", "size": 150, "y": 440,
                                              "sticker": "🔥", "sfx": "impact", "punch": 0.08}),
]
FLASH_BEFORE = ["dream1", "money", "now"]   # white flash at these section starts (ChiliAng 59.2) + whoosh
SFX_DEFAULT = {"name": "whoosh", "label": "pop", "green": "pop", "big": "whoosh", "pill": "pop"}
SFX_GAIN_DB = {"pop": -12.0, "whoosh": -13.0, "ding": -12.0, "impact": -9.0}
MUSIC_LUFS = -22.0           # music bed before ducking; ≈ -27 LUFS under speech (voice is -14 LUFS)
LABEL_FADE_OUT = 0.12        # graphics fade out instead of cutting off
SUB_POP = 0.12               # subtitles pop in line by line


# ------------------------------------------------------------------ stage A: cut list → pieces
@dataclass
class Piece:
    rng: str
    src_in: float
    src_out: float
    out_in: float = 0.0
    zoom: float = 1.0
    jump: str = "range"          # what was removed right before this piece: range | filler | pause

    @property
    def dur(self) -> float:      # source seconds
        return self.src_out - self.src_in

    @property
    def out_dur(self) -> float:  # timeline seconds after the speed-up
        return self.dur / SPEED


def _quiet_runs(db: np.ndarray, hop: float, a: float, b: float) -> list[tuple[float, float]]:
    # 70 ms median: a breath click inside a pause must not split it into short runs that never qualify
    quiet = median_filter(db[int(a / hop):int(b / hop)], size=7, mode="nearest") < PAUSE_DB
    runs, start = [], None
    for i, q in enumerate(np.append(quiet, False)):
        if q and start is None:
            start = i
        elif not q and start is not None:
            runs.append((a + start * hop, min(a + i * hop, b)))
            start = None
    return runs


def plan_pieces(audio: np.ndarray) -> list[Piece]:
    db, hop = frame_energy_db(audio, SR, 0.01)
    pieces: list[Piece] = []
    for name, a, b, *opt in RANGES:
        a, b = snap_cut(audio, a, SR, opt[0] if opt else 0.08), snap_cut(audio, b, SR, 0.08)
        cuts: list[tuple[float, float, str]] = []
        for s, e in _quiet_runs(db, hop, a, b):
            if s <= a + 1e-6:                                   # leading silence
                a = max(a, e - EDGE_KEEP_IN)
            elif e >= b - 1e-6:                                 # trailing silence
                b = min(b, s + EDGE_KEEP_OUT)
            elif e - s >= PAUSE_MIN:
                cuts.append((s + PAUSE_KEEP, e - PAUSE_KEEP, "pause"))
        cuts += [(s, e, "filler") for s, e in FILLER_CUTS if a < s < b]
        cuts.sort()
        t, jump = a, "range"
        for s, e, kind in cuts:
            s, e = snap_cut(audio, s, SR, 0.03), snap_cut(audio, e, SR, 0.03)
            if s <= t:
                t, jump = max(t, e), kind if kind == "filler" else jump
                continue
            pieces.append(Piece(name, t, s, jump=jump))
            t, jump = e, kind
        if b > t:
            pieces.append(Piece(name, t, b, jump=jump))
    out, zoomed = 0.0, True
    for p in pieces:
        n = max(int(round(p.dur / SPEED * FPS)), 1)           # whole output frames keep picture and sound locked
        p.src_out = p.src_in + n * SPEED / FPS
        p.out_in = out
        if p.jump in ("range", "filler"):                     # punch-in alternates on real jump cuts only
            zoomed = not zoomed
        p.zoom = ZOOM_IN if zoomed else 1.0
        out += n / FPS
    return pieces


def render_aroll(pieces: list[Piece], source: Path, work: Path) -> Path:
    parts = []
    for i, p in enumerate(pieces):
        key = hashlib.sha1(f"{p.src_in:.5f}|{p.src_out:.5f}|{p.zoom}|{SPEED}".encode()).hexdigest()[:8]
        part = work / f"piece_{i:03d}_{key}.mov"
        parts.append(part)
        if part.exists():
            continue
        n = int(round(p.out_dur * FPS))
        z, (fx, fy) = p.zoom, FOCUS
        vf = (f"crop=iw/{z}:ih/{z}:(iw-iw/{z})*{fx}:(ih-ih/{z})*{fy},scale={W}:{H}:flags=lanczos,"
              f"setpts=(PTS-STARTPTS)/{SPEED},fps={FPS_NUM}/{FPS_DEN},setsar=1")
        od = n / FPS
        af = (f"atempo={SPEED},atrim=0:{od:.5f},apad=whole_dur={od:.5f},afade=t=in:d=0.012,"
              f"afade=t=out:st={od - 0.012:.5f}:d=0.012,aresample=48000,aformat=channel_layouts=stereo")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{p.src_in:.4f}", "-t", f"{p.dur + 0.05:.4f}",
                        "-i", str(source), "-map", "0:v:0", "-map", "0:a:0", "-vf", vf, "-af", af,
                        "-frames:v", str(n), "-c:v", "libx264", "-crf", "12", "-preset", "fast",
                        "-pix_fmt", "yuv420p", "-c:a", "pcm_s16le", str(part)], check=True)
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
            return p.out_in + (t - p.src_in) / SPEED
    # inside a removed pause / filler (or past an edge): snap to the nearest kept boundary
    best = min(own, key=lambda p: min(abs(t - p.src_in), abs(t - p.src_out)))
    return best.out_in if abs(t - best.src_in) < abs(t - best.src_out) else best.out_in + best.out_dur


def range_span(pieces, rng):
    own = [p for p in pieces if p.rng == rng]
    return own[0].out_in, own[-1].out_in + own[-1].out_dur


def span(pieces, rng: str, a: float, b: float) -> tuple[float, float]:
    """Output window of a source window; `rng` may be "first>last" to run across ranges."""
    r0, r1 = rng.split(">") if ">" in rng else (rng, rng)
    s, e = to_out(pieces, r0, a), to_out(pieces, r1, b)
    return max(s, range_span(pieces, r0)[0]), min(e, range_span(pieces, r1)[1])


def build_cues(pieces):
    cues = [list(span(pieces, rng, a, b)) + [text] for rng, a, b, text in CUES]
    cues.sort()
    for i in range(len(cues) - 1):                     # no gaps / overlaps between consecutive lines
        if cues[i + 1][0] - cues[i][1] < 0.25:
            cues[i][1] = cues[i + 1][0]
    return [tuple(c) for c in cues if c[1] - c[0] > 0.05]


class FadeOut(Layer):
    """Wraps a graphic so it fades out over its last `fade` seconds instead of cutting off."""

    def __init__(self, inner: Layer, fade: float):
        super().__init__(start=inner.start, duration=inner.duration, z=inner.z)
        self.inner, self.fade = inner, fade

    def draw(self, frame, ctx, t):
        k = min(1.0, (self.duration - t) / self.fade) if self.fade > 0 else 1.0
        if k >= 1.0:
            return self.inner.draw(frame, ctx, t)
        base = frame.copy()
        out = self.inner.draw(frame, ctx, t)
        return base * (1 - k) + out * k


def build_overlays(pieces):
    """Graphics, camera motion and SFX events (time, effect, gain_db) on the output timeline."""
    layers, events = [], []
    for rng, a, b, kind, text, o in OVERLAYS:
        s, e = span(pieces, rng, a, b)
        kw = dict(start=s, duration=e - s, z=20)
        if kind == "pill":
            g = D.InterviewQuestionPill(text, **kw)
        elif kind == "small":
            g = D.InterviewSmallLabel(text, y=o.get("y", 262), size=40, **kw)
        elif kind in ("label", "green"):
            g = D.InterviewTopLabel(text, y=o.get("y", 432), size=72, sticker=o.get("sticker"),
                                    style="green" if kind == "green" else "navy",
                                    sticker_side=o.get("side", "right"), **kw)
        elif kind == "big":
            g = D.InterviewBigTitle(text, y=o.get("y", 430), size=o.get("size", 170), sticker=o.get("sticker"),
                                    color=o.get("color", "#111111"), role=o.get("role", "serif_title"), **kw)
        else:
            g = D.InterviewNameTag(text, y=330, size=110, left_sticker=o.get("left"),
                                   right_sticker=o.get("right"), subline=o.get("subline", ""), **kw)
        layers.append(FadeOut(g, LABEL_FADE_OUT))
        effect = o.get("sfx", SFX_DEFAULT.get(kind))
        if effect:
            # whooshes peak ~0.3 s in, so they start early to land on the graphic
            events.append((max(s - (0.25 if effect == "whoosh" else 0.0), 0.0), effect, SFX_GAIN_DB[effect]))
        if o.get("punch"):
            layers.append(ZoomPunch(amount=o["punch"], center=(0.5, 0.36), start=s, duration=e - s, z=-85))
        if o.get("shake"):
            layers.append(CameraShake(intensity=0.012, decay=5.0, rotation=0.8, zoom=1.03,
                                      start=s, duration=0.6, z=-84))
    for rng in FLASH_BEFORE:
        rs, _ = range_span(pieces, rng)
        layers.append(D.WhiteFlash(start=max(rs - 0.07, 0), z=90))
        events.append((max(rs - 0.32, 0.0), "whoosh", SFX_GAIN_DB["whoosh"]))
    # slow push-in over every shot (a shot = pieces between punch-in toggles)
    shot_start, shot_zoom = 0.0, pieces[0].zoom
    for p in pieces[1:] + [None]:
        if p is None or p.zoom != shot_zoom:
            end = p.out_in if p else pieces[-1].out_in + pieces[-1].out_dur
            layers.append(SlowPushIn(amount=PUSH_IN, center=(0.5, 0.36), start=shot_start,
                                     duration=end - shot_start, z=-90))
            if p:
                shot_start, shot_zoom = p.out_in, p.zoom
    return layers, sorted(events)


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
    overlays, events = build_overlays(pieces)
    total = pieces[-1].out_in + pieces[-1].out_dur
    plan = {"speed": SPEED, "aroll_seconds": total, "pieces": [p.__dict__ | {"dur": p.dur} for p in pieces],
            "cues": cues, "sfx": events}
    (work / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=1))
    (work / "subtitles.srt").write_text(srt(cues), encoding="utf-8")
    print(f"pieces={len(pieces)} aroll={total:.2f}s cues={len(cues)} sfx={len(events)}")
    if a.plan_only:
        return

    aroll = render_aroll(pieces, source, work)

    # music bed + sound effects (synthesised, royalty-free)
    music = SFX.write_wav(work / "music_bed.wav", SFX.music_bed(total + 0.5))
    sfx_files = {k: SFX.write_wav(work / f"sfx_{k}.wav", f()) for k, f in SFX.EFFECTS.items()}

    brand = load_brand("dfsc-2027")
    tl = Timeline(W, H, FPS, duration=total, brand=brand)
    tl.add(VideoClipLayer(aroll, duration=total, z=-100))
    tl.add(*overlays)
    tl.add(ImageLayer(ROOT / "projects/dfsc-2027/brand/logos/dreamfactory_watermark.png", x=34, y=60,
                      height=104, duration=total, opacity=0.92, z=40))
    tl.add(D.InterviewSubtitle(cues, y=1400, size=66, pop=SUB_POP, z=30))
    gfx = work / ("graphics_preview.mp4" if a.preview else "graphics.mp4")
    pw, ph = (720, 1280) if a.preview else (W, H)
    tl.render(gfx, width=pw, height=ph, crf=14, preset="fast" if a.preview else "medium",
              progress=lambda d, n: print(f"\rframes {d}/{n}", end="", flush=True) if d % 120 == 0 or d == n else None)
    print()

    # stage D: brand outro (identical in JoshuaChin 0:42 / ChiliAng 1:00) + mix + loudness
    outro = work / f"outro_{pw}.mov"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{a.outro_in}", "-i", a.outro_ref,
                    "-vf", f"scale={pw}:{ph}:flags=lanczos,fps={FPS_NUM}/{FPS_DEN},setsar=1",
                    "-af", "aresample=48000,afade=t=in:d=0.08", "-c:v", "libx264", "-crf", "12", "-preset", "fast",
                    "-pix_fmt", "yuv420p", "-c:a", "pcm_s16le", "-ac", "1", str(outro)], check=True)
    mode = "preview" if a.preview else "final"
    out = reserve_output(a.out_dir, "dfsc2027_nelson_chin_gaochill", mode)
    xf = 0.12   # reference cross-dissolves into the outro over ≈0.12 s (ChiliAng 60.58–60.70)
    inputs = ["-i", str(gfx), "-i", str(aroll), "-i", str(outro), "-i", str(music)]
    chains = [f"[0:v]setpts=PTS-STARTPTS[v0];[2:v]setpts=PTS-STARTPTS[v1];"
              f"[v0][v1]xfade=transition=fade:duration={xf}:offset={total - xf:.4f},format=yuv420p[v]",
              "[1:a]highpass=f=80,afftdn=nr=10:nf=-40,aresample=48000,aformat=channel_layouts=stereo,"
              "loudnorm=I=-14:TP=-2:LRA=9,asplit=2[sp][sc]",
              f"[3:a]aresample=48000,aformat=channel_layouts=stereo,loudnorm=I={MUSIC_LUFS}:TP=-8:LRA=7,"
              f"atrim=0:{total:.4f},afade=t=out:st={total - 1.2:.4f}:d=1.2[mu]",
              "[mu][sc]sidechaincompress=threshold=0.06:ratio=2:attack=20:release=350[mud]"]
    mix = ["[sp]", "[mud]"]
    for i, (t, effect, gain) in enumerate(events):
        inputs += ["-i", str(sfx_files[effect])]
        ms = int(t * 1000)
        chains.append(f"[{4 + i}:a]aresample=48000,aformat=channel_layouts=stereo,volume={gain}dB,"
                      f"adelay={ms}|{ms}[s{i}]")
        mix.append(f"[s{i}]")
    # limiter keeps SFX transients (impact) under the -1.5 dBTP final ceiling
    chains.append("".join(mix) + f"amix=inputs={len(mix)}:duration=first:normalize=0,"
                  "alimiter=limit=0.6:attack=3:release=60:level=false[prog]")
    chains.append("[2:a]aformat=channel_layouts=stereo,loudnorm=I=-15:TP=-2:LRA=9[ou]")
    chains.append(f"[prog][ou]acrossfade=d={xf}[mix];[mix]aresample=48000[a]")
    subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(chains),
                    "-map", "[v]", "-map", "[a]",
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
