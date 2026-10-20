"""Music, sound effects and mix for the talking-head part.

The background music and every sound effect are synthesised here from scratch,
so the soundtrack contains no third-party recordings: it is free for commercial
use and cannot trigger Content ID / rights claims on Facebook or Instagram.

Reference behaviour (video 1, measured after vocal separation): ~99 BPM, F major,
a quiet piano/pad bed ~13 LU under the voice for the first ~70% of the talk, a
fuller groove ~9 LU under it for the rest, SFX only on the emphasised key words,
music handing over to the outro's own soundtrack.

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


# --------------------------------------------------------------------------- sfx
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

    # ---- music: original piece (studio/music.py), quiet bed -> fuller groove at the insight section ----
    import pyloudnorm
    from music import render_music
    build_at = A("in1") - 0.3
    raw_mid = f"{out_dir}/bgm_raw.wav"
    render_music(dur, build_at, A("st10"), raw_mid)
    eq = f"{out_dir}/bgm_eq.wav"
    # leave room for the voice: low cut, small dips at the voice body and presence range
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", raw_mid, "-af",
                    "highpass=f=60,equalizer=f=250:t=q:w=1.2:g=-3,equalizer=f=2500:t=q:w=1.0:g=-3,"
                    "aresample=48000", "-ac", "2", eq], check=True)
    bgm = read_wav(eq)[:, :n]
    bgm = np.pad(bgm, ((0, 0), (0, n - bgm.shape[1])))
    meter = pyloudnorm.Meter(SR)
    sp_lufs = meter.integrated_loudness(sp)
    # reference reel: music ~13 LU under the voice in the quiet part, ~9 LU under it in the full part
    # (its accompaniment stem also carries SFX); targets are set 3 dB hot to pre-compensate ducking,
    # landing at ~14 / ~10 LU under the voice
    k = int(build_at * SR)
    targets = [(slice(0, k), sp_lufs - 11.0), (slice(k, n), sp_lufs - 7.0)]
    gain = np.ones(n)
    for sl, tgt in targets:
        seg = bgm[:, sl]
        cur = meter.integrated_loudness(seg.T)
        gain[sl] = 10 ** ((tgt - cur) / 20)
    xf = int(1.0 * SR)                                  # smooth the step over 1 s
    gain[k - xf // 2:k + xf // 2] = np.linspace(gain[k - xf // 2 - 1], gain[k + xf // 2], xf)
    bgm = bgm * gain
    # gentle ducking under speech
    e = np.sqrt(moving_avg(sp ** 2, 480))
    act = moving_avg((e > 10 ** (-38 / 20)).astype(float), int(0.25 * SR))
    bgm = bgm * 10 ** (-3 * np.clip(act, 0, 1) / 20)
    t = np.arange(n) / SR
    bgm = bgm * np.clip((dur - t) / 1.2, 0, 1)          # fade before the outro's own music
    write_wav(f"{out_dir}/bgm.wav", bgm)

    # ---- sound effects: only on the key words (the big serif emphasis titles) ----
    sfx = np.zeros((2, n))
    cues = []
    for s in titles:
        if s["type"] == "serif":
            t0 = A(s["start"])
            place(sfx, sfx_impact(), t0 - 0.08)
            place(sfx, sfx_glitch(), t0 - 0.08)
            cues.append((round(t0, 2), "impact+glitch", s["text"]))
    write_wav(f"{out_dir}/sfx.wav", sfx)
    json.dump(sorted(cues), open(f"{out_dir}/sfx_cues.json", "w"), ensure_ascii=False, indent=0)

    # ---- mix: levels relative to speech, then loudness-normalise to -14 LUFS (reference: -13.9) ----
    mix = np.stack([sp, sp]) + bgm + sfx * 0.6
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
