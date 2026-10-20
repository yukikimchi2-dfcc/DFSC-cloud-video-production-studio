"""Music, sound effects and mix for the talking-head part.

The background music and every sound effect are synthesised here from scratch,
so the soundtrack contains no third-party recordings: it is free for commercial
use and cannot trigger Content ID / rights claims on Facebook or Instagram.

Reference behaviour (video 1): a quiet pad bed under the first ~70% of the talk,
a fuller groove in the last third, SFX on title/keyword moments, music handing
over to the outro's own soundtrack.

usage: python audio.py <edl.json> <titles.py> <speech.wav> <out_dir>
  -> out_dir/bgm.wav, sfx.wav, speech_proc.wav, mix_talk.wav (48 kHz stereo)
"""
import importlib.util
import json
import os
import subprocess
import sys
import wave

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from render import Anchors  # noqa: E402

SR = 48000
rng = np.random.default_rng(7)


def write_wav(path, x):
    x = np.atleast_2d(x)
    if x.shape[0] < x.shape[1]:
        x = x.T
    with wave.open(path, "w") as w:
        w.setnchannels(x.shape[1]); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())


def read_wav(path):
    w = wave.open(path)
    a = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    return a.reshape(-1, w.getnchannels()).T


def lowpass(x, fc):
    a = np.exp(-2 * np.pi * fc / SR)
    from scipy.signal import lfilter
    return lfilter([1 - a], [1, -a], x)


def moving_avg(x, k):
    c = np.cumsum(np.concatenate([np.zeros(k // 2 + 1), x, np.zeros(k)]))
    return (c[k:k + len(x)] - c[:len(x)]) / k


def midi(n):
    return 440.0 * 2 ** ((n - 69) / 12)


# --------------------------------------------------------------------------- music
def synth_bgm(dur, build_at, bpm=96):
    """Warm, positive pop-corporate bed: pad + e-piano arpeggio, then bass + drums."""
    n = int(round(dur * SR))
    t = np.arange(n) / SR
    beat = 60 / bpm
    bar = 4 * beat
    # D major: D  A  Bm  G   (I V vi IV)
    prog = [(62, [62, 66, 69]), (57, [61, 64, 69]), (59, [62, 66, 71]), (55, [62, 67, 71])]
    L = np.zeros(n); R = np.zeros(n)
    nbars = int(np.ceil(dur / bar)) + 1
    env_build = np.clip((t - build_at) / (2 * bar), 0, 1)

    for b in range(nbars):
        root, chord = prog[b % 4]
        s0, s1 = int(b * bar * SR), int((b + 1) * bar * SR)
        if s0 >= n:
            break
        s1 = min(s1, n)
        tt = np.arange(s1 - s0) / SR
        # pad: detuned saw-ish (few harmonics), slow swell
        pad = np.zeros(len(tt))
        for k, note in enumerate(chord):
            for det in (-0.12, 0.12):
                f = midi(note) * 2 ** (det / 12)
                for h in range(1, 6):
                    pad += np.sin(2 * np.pi * f * h * tt + k + h) / (h * 1.6)
        sw = np.minimum(1, tt / 0.6) * np.minimum(1, (bar - tt) / 0.25 + 0.4)
        pad = pad * sw * 0.035
        L[s0:s1] += pad; R[s0:s1] += np.roll(pad, 240)
        # e-piano arpeggio (8ths), chord tones up an octave
        arp = [chord[0] + 12, chord[1] + 12, chord[2] + 12, chord[1] + 12] * 2
        for i, note in enumerate(arp):
            a0 = s0 + int(i * beat / 2 * SR)
            if a0 >= n:
                break
            ln = min(int(0.9 * SR), n - a0)
            te = np.arange(ln) / SR
            f = midi(note)
            tone = (np.sin(2 * np.pi * f * te) + 0.35 * np.sin(2 * np.pi * 2 * f * te) * np.exp(-te * 9)
                    + 0.1 * np.sin(2 * np.pi * 3 * f * te) * np.exp(-te * 14))
            tone *= np.exp(-te * 4.2) * np.minimum(1, te / 0.004) * (0.075 if i % 2 == 0 else 0.055)
            pan = 0.35 if i % 2 else -0.35
            L[a0:a0 + ln] += tone * (1 - pan); R[a0:a0 + ln] += tone * (1 + pan)
        # bass + drums only after the build point
        for q in range(4):
            q0 = s0 + int(q * beat * SR)
            if q0 >= n:
                break
            gb = env_build[q0]
            if gb <= 0:
                continue
            ln = min(int(beat * 0.95 * SR), n - q0)
            te = np.arange(ln) / SR
            bass = np.sin(2 * np.pi * midi(root - 24) * te) * np.exp(-te * 3) * np.minimum(1, te / 0.01) * 0.16 * gb
            L[q0:q0 + ln] += bass; R[q0:q0 + ln] += bass
            # kick on 1 and 3, clap on 2 and 4
            kl = min(int(0.25 * SR), n - q0)
            tk = np.arange(kl) / SR
            if q % 2 == 0:
                kick = np.sin(2 * np.pi * (50 + 90 * np.exp(-tk * 30)) * tk) * np.exp(-tk * 14) * 0.22 * gb
                L[q0:q0 + kl] += kick; R[q0:q0 + kl] += kick
            else:
                cl = lowpass(rng.standard_normal(kl), 3500) * np.exp(-tk * 28) * 0.10 * gb
                L[q0:q0 + kl] += cl; R[q0:q0 + kl] += cl
            # off-beat hat
            h0 = q0 + int(beat / 2 * SR)
            hl = min(int(0.05 * SR), max(0, n - h0))
            if hl > 0:
                th = np.arange(hl) / SR
                hat = np.diff(np.concatenate([[0], rng.standard_normal(hl)])) * np.exp(-th * 80) * 0.025 * gb
                L[h0:h0 + hl] += hat * 0.8; R[h0:h0 + hl] += hat * 1.2
    out = np.stack([L, R])
    fade = np.minimum(1, t / 1.0) * np.clip((dur - t) / 1.2, 0, 1)
    return out * fade


# --------------------------------------------------------------------------- sfx
def sfx_whoosh(d=0.38, lo=400, hi=4000, gain=0.35):
    n = int(d * SR); te = np.arange(n) / SR
    noise = rng.standard_normal(n)
    out = np.zeros(n)
    # sweep a resonant band (chunked one-pole bandpass approximation)
    chunk = 256
    for i in range(0, n, chunk):
        p = i / n
        fc = lo * (hi / lo) ** p
        seg = noise[i:i + chunk]
        out[i:i + chunk] = lowpass(seg, fc) - lowpass(seg, fc * 0.45)
    env = np.sin(np.pi * np.clip(te / d, 0, 1)) ** 1.5
    return out * env * gain * 3


def sfx_pop(gain=0.3):
    n = int(0.09 * SR); te = np.arange(n) / SR
    f = 900 * np.exp(-te * 25) + 300
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-te * 40) * gain


def sfx_ding(gain=0.12):
    n = int(0.9 * SR); te = np.arange(n) / SR
    x = sum(np.sin(2 * np.pi * f * te) * a * np.exp(-te * k)
            for f, a, k in [(2637, 1, 5), (3951, 0.5, 7), (5274, 0.3, 10), (7040, 0.15, 14)])
    return x * np.minimum(1, te / 0.002) * gain


def sfx_impact(gain=0.32):
    n = int(1.1 * SR); te = np.arange(n) / SR
    boom = np.sin(2 * np.pi * (40 + 110 * np.exp(-te * 12)) * te) * np.exp(-te * 4.5)
    crack = lowpass(rng.standard_normal(n), 6000) * np.exp(-te * 35)
    shimmer = sum(np.sin(2 * np.pi * f * te + p) for f, p in [(3136, 0), (4186, 1), (5588, 2)]) * \
        np.exp(-te * 3) * np.minimum(1, te / 0.05) * 0.06
    return (boom * 0.8 + crack * 0.35 + shimmer) * gain


def sfx_glitch(gain=0.12):
    n = int(0.22 * SR); te = np.arange(n) / SR
    sq = np.sign(np.sin(2 * np.pi * 180 * te)) * (rng.random(n) > 0.3)
    crush = np.repeat(rng.standard_normal(n // 64 + 1), 64)[:n]
    gate = (np.floor(te * 40) % 2 == 0)
    return (sq * 0.5 + crush * 0.5) * gate * np.exp(-te * 8) * gain


def sfx_thump(gain=0.45):
    n = int(0.5 * SR); te = np.arange(n) / SR
    return np.sin(2 * np.pi * (45 + 60 * np.exp(-te * 20)) * te) * np.exp(-te * 9) * gain


def place(buf, clip, t, pan=0.0):
    s = int(t * SR)
    if s < 0:
        clip = clip[-s:]; s = 0
    e = min(buf.shape[1], s + len(clip))
    if e <= s:
        return
    buf[0, s:e] += clip[:e - s] * (1 - pan)
    buf[1, s:e] += clip[:e - s] * (1 + pan)


def load_mod(path):
    spec = importlib.util.spec_from_file_location("m", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main(edl_path, titles_path, speech_path, out_dir):
    edl = json.load(open(edl_path))
    dur = edl["frames"] / edl["fps"]
    A = Anchors(edl)
    n = int(round(dur * SR))
    titles = load_mod(titles_path).TITLES

    # ---- speech: clean-up chain (HPF, gentle denoise, de-ess-ish, compression) ----
    proc = f"{out_dir}/speech_proc.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", speech_path, "-af",
                    "highpass=f=80,afftdn=nr=8:nf=-38,equalizer=f=6500:t=q:w=1.5:g=-2,"
                    "acompressor=threshold=-20dB:ratio=2.5:attack=8:release=120:makeup=2,"
                    "aresample=48000", "-ac", "1", proc], check=True)
    sp = read_wav(proc)[0][:n]
    sp = np.pad(sp, (0, n - len(sp)))

    # ---- music: build into the fuller groove at the insight section (~2/3 in) ----
    build_at = A("in1") - 0.3
    bgm = synth_bgm(dur, build_at)[:, :n]
    # duck under speech (smoothed speech envelope)
    e = np.sqrt(moving_avg(sp ** 2, 480))
    act = moving_avg((e > 10 ** (-38 / 20)).astype(float), int(0.25 * SR))
    duck = 10 ** (-5 * np.clip(act, 0, 1) / 20)
    bgm = bgm * duck
    write_wav(f"{out_dir}/bgm.wav", bgm)

    # ---- sound effects on title / keyword moments ----
    sfx = np.zeros((2, n))
    cues = []
    for s in titles:
        t0 = A(s["start"])
        typ = s["type"]
        if typ == "serif":
            place(sfx, sfx_impact(), t0 - 0.08); place(sfx, sfx_glitch(), t0 - 0.08); cues.append((t0, "impact+glitch"))
        elif typ == "name":
            place(sfx, sfx_whoosh(0.45, gain=0.4), t0 - 0.08); place(sfx, sfx_ding(), t0 + 0.25)
            place(sfx, sfx_pop(), t0 + 0.6, -0.4); place(sfx, sfx_pop(), t0 + 0.85, 0.4)
            cues.append((t0, "whoosh+ding+pops"))
        elif typ == "header":
            place(sfx, sfx_ding(0.1), max(0.05, t0 + 0.3)); cues.append((t0, "ding"))
        elif typ == "rows":
            for a, _ in s["rows"]:
                place(sfx, sfx_whoosh(0.25, 800, 5000, 0.22), A(a) - 0.04); cues.append((A(a), "swish"))
            place(sfx, sfx_pop(0.35), A(s["check_at"])); cues.append((A(s["check_at"]), "pop"))
        elif typ == "box":
            if s["size"] == "L" or s["style"] == "tag":
                place(sfx, sfx_whoosh(), t0 - 0.06); cues.append((t0, "whoosh"))
                if s["style"] != "tag":
                    place(sfx, sfx_ding(), t0 + 0.25)
            else:
                place(sfx, sfx_whoosh(0.25, 800, 5000, 0.2), t0 - 0.04); cues.append((t0, "swish"))
        if s.get("emoji") and typ in ("box", "header"):
            place(sfx, sfx_pop(0.22), t0 + 0.3, 0.3)
    for p in edl["phrases"]:
        if p.get("fx") == "glitch":
            place(sfx, sfx_glitch(), p["start"]); cues.append((p["start"], "glitch"))
        elif p.get("fx") == "shake":
            place(sfx, sfx_thump(), p["start"]); cues.append((p["start"], "thump"))
        elif p.get("fx") == "blur":
            place(sfx, sfx_whoosh(0.5, 300, 3000, 0.4), p["start"] - 0.25); cues.append((p["start"], "whoosh"))
    write_wav(f"{out_dir}/sfx.wav", sfx)
    json.dump(sorted(cues), open(f"{out_dir}/sfx_cues.json", "w"), ensure_ascii=False, indent=0)

    # ---- mix: levels relative to speech, then loudness-normalise to -14 LUFS (reference: -13.9) ----
    mix = np.stack([sp, sp]) + bgm * 0.55 + sfx * 0.6
    tail = int(0.25 * SR)
    mix[:, -tail:] *= np.linspace(1, 0.6, tail)        # hand over to the outro cross-fade
    write_wav(f"{out_dir}/mix_raw.wav", mix * 0.7)
    stats = subprocess.run(["ffmpeg", "-hide_banner", "-i", f"{out_dir}/mix_raw.wav", "-af",
                            "loudnorm=I=-14:TP=-1.5:LRA=9:print_format=json", "-f", "null", "-"],
                           capture_output=True, text=True).stderr
    js = json.loads(stats[stats.rindex("{"):stats.rindex("}") + 1])
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", f"{out_dir}/mix_raw.wav", "-af",
                    f"loudnorm=I=-14:TP=-1.5:LRA=9:measured_I={js['input_i']}:measured_TP={js['input_tp']}:"
                    f"measured_LRA={js['input_lra']}:measured_thresh={js['input_thresh']}:linear=true,"
                    "aresample=48000", "-ar", "48000", f"{out_dir}/mix_talk.wav"], check=True)
    print("cues", len(cues), "measured", js["input_i"], "LUFS -> -14")


if __name__ == "__main__":
    main(*sys.argv[1:5])
