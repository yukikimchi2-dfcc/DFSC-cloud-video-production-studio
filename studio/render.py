"""Render the styled talking-head video (no audio) from an A-roll + EDL + title plan.

usage: python render.py <edl.json> <titles.py> <aroll.mp4> <logo_white.png> <out.mp4>
                        [--frames 10,200,...  (writes PNG previews instead of a video)]
                        [--no-overlays        (text-free A-roll: framing + cut effects only)]
                        [--titles-pack DIR    (each title as a transparent MOV + timecode sheet)]
"""
import importlib.util
import json
import math
import os
import random
import re
import subprocess
import sys

import cv2
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(__file__))
import gfx  # noqa: E402

W, H = 1080, 1920
ZOOM = {"wide": 1.10, "close": 1.27}   # punch-in levels (reference alternates two framings)
PUSH = 0.025                           # slow push-in over a phrase (motion)
EYE_Y = 0.44                           # face centre lands at 44% of frame height
LOGO_BOX = (35, 62, 172)               # x, y, width - measured on the reference
SUB_MAX_W = 960


def load_mod(path):
    spec = importlib.util.spec_from_file_location("m", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# --------------------------------------------------------------------------- anchors
class Anchors:
    def __init__(self, edl):
        self.ph = {p["id"]: p for p in edl["phrases"]}

    def __call__(self, spec):
        m = re.match(r"^([a-z0-9]+)(\.end|:[^+-]+)?([+-][0-9.]+)?$", spec)
        if not m:
            raise ValueError(spec)
        p = self.ph[m.group(1)]
        t = p["start"]
        if m.group(2) == ".end":
            t = p["end"]
        elif m.group(2):
            ch = m.group(2)[1:]
            idx = next(i for i, u in enumerate(p["units"]) if u.startswith(ch))
            t = p["unit_times"][idx]
        return t + float(m.group(3) or 0)


# --------------------------------------------------------------------------- framing
def face_track(aroll, edl):
    """Median face centre per phrase (Haar cascade on a few frames of each clip)."""
    cas = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    cap = cv2.VideoCapture(aroll)
    per_phrase = {}
    for c in edl["clips"]:
        n = c["src_out_f"] - c["src_in_f"]
        for k in (0.25, 0.5, 0.75):
            cap.set(cv2.CAP_PROP_POS_FRAMES, c["out_f"] + int(n * k))
            ok, fr = cap.read()
            if not ok:
                continue
            g = cv2.cvtColor(cv2.resize(fr, (540, 960)), cv2.COLOR_BGR2GRAY)
            faces = cas.detectMultiScale(g, 1.1, 6, minSize=(80, 80))
            if len(faces):
                x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
                per_phrase.setdefault(c["phrase"], []).append(((x + w / 2) * 2, (y + h / 2) * 2, w * 2))
    out, last = {}, (540, 760, 260)
    for p in edl["phrases"]:
        v = per_phrase.get(p["id"])
        if v:
            last = tuple(np.median(np.array(v), 0))
        out[p["id"]] = last
    return out


def frame_matrix(face, zoom):
    cx, cy, _ = face
    hw, hh = W / 2 / zoom, H / zoom
    cx = min(max(cx, hw), W - hw)                    # keep the crop inside the source
    top = cy - EYE_Y * H / zoom
    top = min(max(top, 0), H - hh)
    return np.float32([[zoom, 0, -zoom * (cx - hw)], [0, zoom, -zoom * top]])


# --------------------------------------------------------------------------- compositing
def blend(frame, rgba, x, y, alpha=1.0):
    """frame: uint8 HxWx3 or HxWx4 (modified in place); rgba: float 0..1."""
    x, y = int(round(x)), int(round(y))
    h, w = rgba.shape[:2]
    x0, y0, x1, y1 = max(0, x), max(0, y), min(W, x + w), min(H, y + h)
    if x0 >= x1 or y0 >= y1:
        return
    s = rgba[y0 - y:y1 - y, x0 - x:x1 - x]
    a = s[..., 3:4] * alpha
    d = frame[y0:y1, x0:x1].astype(np.float32)
    if frame.shape[2] == 4:                      # transparent layer: "over" compositing
        da = d[..., 3:4] / 255
        oa = a + da * (1 - a)
        rgb = (s[..., :3] * 255 * a + d[..., :3] * da * (1 - a)) / np.maximum(oa, 1e-6)
        frame[y0:y1, x0:x1] = np.concatenate([rgb, oa * 255], 2).astype(np.uint8)
        return
    frame[y0:y1, x0:x1] = (d * (1 - a) + s[..., :3] * 255 * a).astype(np.uint8)


def export_title_pack(titles, fps, out_dir):
    """Every title as its own transparent clip (MOV, PNG codec), full 1080x1920 canvas so it
    drops in place in any editor; plus cue sheet with record timecodes."""
    import csv
    os.makedirs(out_dir, exist_ok=True)
    rows = []
    for n, tt in enumerate(titles, 1):
        f0, f1 = int(round(tt.t0 * fps)), int(round(tt.t1 * fps))
        s = tt.s
        label = re.sub(r"[\[\]\s/：:・]", "", s.get("text") or s.get("name") or s.get("left", "")) or s["type"]
        name = f"{n:02d}_{s['type']}_{label}.mov"
        enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}",
                                "-r", "24000/1001", "-i", "-", "-c:v", "png", "-pix_fmt", "rgba",
                                f"{out_dir}/{name}"], stdin=subprocess.PIPE)
        for f in range(f0, f1 + 1):
            frame = np.zeros((H, W, 4), np.uint8)
            tt.draw(frame, f / fps)
            enc.stdin.write(frame.tobytes())
        enc.stdin.close()
        enc.wait()
        sec = lambda fr: f"{fr // fps // 60:02.0f}:{fr / fps % 60:06.3f}"  # noqa: E731
        rows.append([name, f0, f1 + 1 - f0, sec(f0), sec(f1 + 1), s["type"], s.get("text") or s.get("name", ""),
                     s.get("emoji", "")])
    with open(f"{out_dir}/titles_timecodes.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["file", "start frame (23.976)", "length frames", "start mm:ss", "end mm:ss", "type", "text", "emoji"])
        w.writerows(rows)
    print(f"{len(rows)} title clips -> {out_dir}")


def runs_from(text):
    """'創業很[辛苦]' -> [(text, color)]"""
    runs = []
    for part in re.split(r"(\[[^\]]+\])", text):
        if not part:
            continue
        if part.startswith("["):
            runs.append((part[1:-1], gfx.TITLE_GREEN))
        else:
            runs.append((part, gfx.WHITE))
    return runs


SIZES = {"L": 108, "M": 64, "S": 50}


class Title:
    def __init__(self, spec, anchors):
        self.s = spec
        self.t0, self.t1 = anchors(spec["start"]), anchors(spec["end"])
        self.anchors = anchors
        typ = spec["type"]
        self.items = []
        rnd = random.Random(hash(spec.get("text", spec.get("name", ""))) & 0xFFFF)
        if typ == "box":
            style = spec["style"]
            runs = runs_from(spec["text"])
            if style == "tag":
                runs = [(t, gfx.TAG_GREY if c == gfx.TITLE_GREEN else gfx.TAG_TEXT) for t, c in runs]
            if style == "green":
                runs = [(t, gfx.WHITE) for t, _ in runs]
            box = gfx.TextBox(runs, style=style, size=SIZES[spec["size"]],
                              kind="sans_black" if spec["size"] != "S" else "sans_bold")
            self.box, self.cy = box, spec["cy"]
        elif typ == "header":
            runs = [(spec["left"], gfx.TITLE_GREEN), ("　　", gfx.WHITE), (spec["right"], gfx.WHITE)]
            self.box, self.cy = gfx.TextBox(runs, style="navy", size=58, kind="sans_black"), 383
        elif typ == "serif":
            fill = gfx.TITLE_GREEN if spec.get("fill") == "green" else gfx.WHITE
            self.word = gfx.SerifWord(spec["text"], size=168, fill=fill)
            self.cy = spec.get("cy", 395)
            self.stars = [(rnd.uniform(-0.6, 0.6), rnd.uniform(-1.1, 0.9), rnd.uniform(0, 0.9),
                           rnd.randint(28, 60)) for _ in range(9)]
        elif typ == "name":
            self.box = gfx.TextBox([(spec["name"], gfx.WHITE)], style="green", size=88, kind="sans_black")
            self.tag = gfx.TextBox([(spec["tag"], gfx.TAG_TEXT)], style="tag", size=44, kind="sans_black",
                                   pad_x=26, pad_y=16)
        elif typ == "rows":
            self.rows = [(anchors(a), gfx.TextBox(runs_from(txt), style="navy", size=46, kind="sans_black",
                                                  pad_x=22, pad_y=12)) for a, txt in spec["rows"]]
            self.check_t = anchors(spec["check_at"])

    def active(self, t):
        return self.t0 - 0.01 <= t <= self.t1 + 0.01

    def draw(self, frame, t):
        s, lt, dur = self.s, t - self.t0, self.t1 - self.t0
        typ = s["type"]
        if typ in ("box", "header"):
            b = self.box
            img = b.render(lt if typ == "box" else max(lt, 1.0), dur if typ == "box" else max(dur, 1.0))
            x, y = int(W / 2 - b.w / 2), int(self.cy - b.h / 2)
            blend(frame, img, x, y)
            if s["type"] == "box" and s.get("style") != "tag":
                star = np.zeros((140, 140, 4), np.float32)
                gfx.render_star(star, lt - 0.22, 0.6, 70, 70, size=46)
                blend(frame, star, x + b.w - 70, y - 70)
            if s.get("emoji"):
                left = s.get("emoji_side") == "left"
                ex = x - 85 if left else x + b.w + 85
                ey = y + 12 if typ == "box" else y - 10
                self._sticker(frame, s["emoji"], lt - 0.3, dur - 0.3, ex, ey, 150 if b.h > 150 else 120)
        elif typ == "serif":
            canvas = np.zeros((420, W, 4), np.float32)
            self.word.render(lt, dur, canvas, W / 2, 210)
            for dx, dy, st, sz in self.stars:                    # gold sparkle burst, twinkling
                ph = (lt - st) % 1.2
                gfx.render_star(canvas, ph, 0.7, W / 2 + dx * self.word.w, 210 + dy * 150, size=sz, gold=True)
            if lt > dur - 4 / 24:
                canvas[..., 3] *= max(0.0, (dur - lt) / (4 / 24))
            blend(frame, canvas, 0, int(self.cy - 210))
            if s.get("emoji"):
                left = s.get("emoji_side") == "left"
                ex = W / 2 - self.word.w / 2 - 70 if left else W / 2 + self.word.w / 2 + 75
                self._sticker(frame, s["emoji"], lt - 0.35, dur - 0.35, ex, self.cy - 45, 140)
            if s.get("emoji2"):
                self._sticker(frame, s["emoji2"], lt - 0.5, dur - 0.5, W / 2 + self.word.w / 2 + 75,
                              self.cy - 10, 140, phase=1.3)
        elif typ == "name":
            b, tg = self.box, self.tag
            bx, by = int(W / 2 - b.w / 2), 220
            blend(frame, b.render(lt, dur), bx, by)
            star = np.zeros((140, 140, 4), np.float32)
            gfx.render_star(star, lt - 0.22, 0.6, 70, 70, size=46)
            blend(frame, star, bx + b.w - 70, by - 70)
            blend(frame, tg.render(lt - 0.35, dur - 0.35), int(W / 2 - tg.w / 2), by + b.h + 24)
            self._sticker(frame, s["left"], lt - 0.6, dur - 0.6, 115, 470, 150)
            self._sticker(frame, s["right"], lt - 0.85, dur - 0.85, 965, 460, 150, phase=2.0)
        elif typ == "rows":
            ys = [300, 410, 520]
            xl = min(int(W / 2 - rb.w / 2) for _, rb in self.rows)
            for k, (ta, rb) in enumerate(self.rows):
                if t < ta:
                    continue
                img = rb.render(t - ta, self.t1 - ta)
                blend(frame, img, int(W / 2 - rb.w / 2), int(ys[k] - rb.h / 2))
            self._sticker(frame, s["icon"], lt, dur, xl - 75, 330, 130)
            if t >= self.check_t:
                last = self.rows[-1][1]
                self._sticker(frame, "✅", t - self.check_t, self.t1 - self.check_t,
                              int(W / 2 + last.w / 2 + 70), ys[len(self.rows) - 1], 110)

    def _sticker(self, frame, ch, lt, dur, cx, cy, size, phase=0.0):
        if lt < 0:
            return
        c = np.zeros((size * 2, size * 2, 4), np.float32)
        gfx.render_sticker(c, ch, lt, dur, size, size, size, phase)
        blend(frame, c, int(cx - size), int(cy - size))


# --------------------------------------------------------------------------- subtitles
class Subtitles:
    def __init__(self, edl):
        self.items = []
        phrases = edl["phrases"]
        for n, p in enumerate(phrases):
            units, times = p["units"], p["unit_times"]
            kwmask = [False] * len(units)
            joined = "".join(units)
            for kw in p["kw"]:
                pos = joined.find(kw)
                if pos < 0:
                    continue
                acc = 0
                for i, u in enumerate(units):
                    if pos <= acc < pos + len(kw):
                        kwmask[i] = True
                    acc += len(u)
            # split into lines that fit
            lines = [(0, len(units))]
            f = gfx.font("sans_bold", gfx.SubtitleLine.SIZE)
            if f.getlength("".join(units)) > SUB_MAX_W:
                cut = next((i + 1 for i, u in enumerate(units) if u == "，"), None)
                if cut is None:
                    acc, cut = 0, len(units) // 2
                    for i, u in enumerate(units):
                        acc += f.getlength(u)
                        if acc > f.getlength("".join(units)) / 2:
                            cut = i
                            break
                lines = [(0, cut), (cut, len(units))]
            end = phrases[n + 1]["start"] if n + 1 < len(phrases) else p["end"]
            end = min(end, p["end"] + 0.25)
            for a, b in lines:
                u = units[a:b]
                if u and u[-1] == "，":                       # no trailing comma on a line
                    b -= 1
                    u = units[a:b]
                self.items.append(dict(line=gfx.SubtitleLine(u, kwmask[a:b]), times=times[a:b],
                                       start=times[a], end=end, phrase=p["id"]))
        # a split phrase: first line ends when the second line starts
        for i in range(len(self.items) - 1):
            if self.items[i]["phrase"] == self.items[i + 1]["phrase"]:
                self.items[i]["end"] = self.items[i + 1]["start"]

    def draw(self, frame, t):
        for it in self.items:
            if it["start"] - 0.001 <= t < it["end"]:
                alphas = [float(np.clip((t - ut) / (2 / 24) + 0.5, 0, 1)) for ut in it["times"]]
                ln = it["line"]
                blend(frame, ln.frame(alphas), ln.x, ln.y)


# --------------------------------------------------------------------------- effects
def fx_glitch(img, k, n, seed):
    """RGB split + slice displacement, decaying over n frames."""
    rnd = random.Random(seed * 31 + k)
    amt = (1 - k / n)
    d = int(22 * amt) + 2
    out = img.copy()
    out[..., 0] = np.roll(img[..., 0], d, axis=1)
    out[..., 2] = np.roll(img[..., 2], -d, axis=1)
    for _ in range(int(5 * amt) + 1):
        y0 = rnd.randint(0, H - 80)
        h = rnd.randint(12, 70)
        out[y0:y0 + h] = np.roll(out[y0:y0 + h], rnd.randint(-40, 40), axis=1)
    return out


def fx_shake(k, n, seed):
    rnd = random.Random(seed * 17 + k)
    a = 22 * (1 - k / n)
    return rnd.uniform(-a, a), rnd.uniform(-a, a)


def main():
    edl_path, titles_path, aroll, logo_path, out = sys.argv[1:6]
    preview = None
    if "--frames" in sys.argv:
        preview = [int(x) for x in sys.argv[sys.argv.index("--frames") + 1].split(",")]
    overlays = "--no-overlays" not in sys.argv
    edl = json.load(open(edl_path))
    fps = edl["fps"]
    anchors = Anchors(edl)
    if "--titles-pack" in sys.argv:
        titles = [Title(s, anchors) for s in load_mod(titles_path).TITLES]
        export_title_pack(titles, fps, sys.argv[sys.argv.index("--titles-pack") + 1])
        return
    titles = [Title(s, anchors) for s in load_mod(titles_path).TITLES]
    subs = Subtitles(edl)
    faces = face_track(aroll, edl)

    logo = Image.open(logo_path)
    lx, ly, lw = LOGO_BOX
    sc = lw / (logo.width - 24)                       # extracted logo carries a 12px margin
    logo = logo.resize((int(logo.width * sc), int(logo.height * sc)), Image.LANCZOS)
    # faint soft shadow so the logo stays legible on a busy backdrop
    from PIL import ImageFilter
    sh = logo.split()[3].filter(ImageFilter.GaussianBlur(5)).point(lambda v: int(v * 0.45))
    base = Image.new("RGBA", logo.size, (0, 0, 0, 0))
    base.putalpha(sh)
    base.alpha_composite(logo)
    logo_np = np.asarray(base, np.float32) / 255
    logo_xy = (lx - int(12 * sc), ly - int(12 * sc))

    phrases = edl["phrases"]
    ph_of_frame = np.zeros(edl["frames"], np.int32)
    for i, p in enumerate(phrases):
        a = int(round(p["start"] * fps))
        ph_of_frame[a:] = i
    # cut effects: phrase fx + glitch whenever a serif title enters
    fx_at = []
    for i, p in enumerate(phrases):
        if p.get("fx"):
            fx_at.append((int(round(p["start"] * fps)), p["fx"], i))
    for i, tt in enumerate(titles):
        if tt.s["type"] == "serif":
            fx_at.append((int(round(tt.t0 * fps)), "glitch", 100 + i))

    dec = subprocess.Popen(["ffmpeg", "-v", "error", "-i", aroll, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                           stdout=subprocess.PIPE)
    enc = None
    if preview is None:
        enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                                "-s", f"{W}x{H}", "-r", "24000/1001", "-i", "-", "-c:v", "libx264",
                                "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p",
                                "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
                                "-movflags", "+faststart", out], stdin=subprocess.PIPE)
    prev_src = None
    for f in range(edl["frames"]):
        raw = dec.stdout.read(W * H * 3)
        if len(raw) < W * H * 3:
            break
        if preview is not None and f not in preview and f + 1 not in preview:
            continue
        src = np.frombuffer(raw, np.uint8).reshape(H, W, 3)
        t = f / fps
        p = phrases[ph_of_frame[f]]
        z = ZOOM[p["zoom"]] * (1 + PUSH * min(1.0, (t - p["start"]) / max(0.5, p["end"] - p["start"])))
        M = frame_matrix(faces[p["id"]], z)
        # effects on the picture
        active = [(f - f0, kind, sd) for f0, kind, sd in fx_at if 0 <= f - f0 < 8]
        for k, kind, sd in active:
            if kind == "shake":
                dx, dy = fx_shake(k, 8, sd)
                M = M.copy(); M[0, 2] += dx; M[1, 2] += dy
                M[:, :2] *= 1.04; M[0, 2] -= W * 0.02; M[1, 2] -= H * 0.02
        frame = cv2.warpAffine(src, M, (W, H), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT)
        for k, kind, sd in [(f - f0, kind, sd) for f0, kind, sd in fx_at if -3 <= f - f0 < 5]:
            if kind == "blur":                         # ghost + zoom-blur transition (reference 0:40)
                s = 1 - abs(k + 0.5) / 4.5
                ghost = cv2.warpAffine(frame, np.float32([[1.08, 0, -W * 0.04], [0, 1.08, -H * 0.04]]),
                                       (W, H), borderMode=cv2.BORDER_REFLECT)
                frame = cv2.addWeighted(frame, 1 - 0.45 * s, ghost, 0.45 * s, 12 * s)
                frame = cv2.GaussianBlur(frame, (0, 0), 1 + 9 * s)
        if overlays:
            blend(frame, logo_np, *logo_xy)
            for tt in titles:
                if tt.active(t):
                    tt.draw(frame, t)
            subs.draw(frame, t)
        for k, kind, sd in active:
            if kind == "glitch" and k < 5:
                frame = fx_glitch(frame, k, 5, sd)
        if preview is not None:
            if f in preview:
                Image.fromarray(frame).save(f"{out}_{f:05d}.png")
            continue
        enc.stdin.write(frame.tobytes())
        if f % 120 == 0:
            print(f"frame {f}/{edl['frames']}", flush=True)
    dec.stdout.close()
    if enc:
        enc.stdin.close()
        enc.wait()


if __name__ == "__main__":
    main()
