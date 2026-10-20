"""Procedurally synthesised sound effects and a music bed.

Everything here is generated from oscillators and noise, so it is original and royalty-free
(Notion 剪辑 SOP: 只用无版权音乐). All functions return float32 stereo arrays (n, 2) at `SR`.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from scipy import signal
from scipy.io import wavfile

SR = 48000


def _t(seconds: float) -> np.ndarray:
    return np.arange(int(seconds * SR)) / SR


def _stereo(x: np.ndarray, pan: float = 0.0) -> np.ndarray:
    """Equal-power pan, pan in [-1, 1]."""
    a = (pan + 1) * np.pi / 4
    return np.stack([x * np.cos(a), x * np.sin(a)], axis=1).astype(np.float32)


def _norm(x: np.ndarray, peak_db: float = -1.0) -> np.ndarray:
    p = np.max(np.abs(x)) or 1.0
    return (x / p * 10 ** (peak_db / 20)).astype(np.float32)


def _bandpass(x: np.ndarray, lo: float, hi: float, order: int = 2) -> np.ndarray:
    sos = signal.butter(order, [lo, hi], btype="band", fs=SR, output="sos")
    return signal.sosfilt(sos, x)


def _lowpass(x: np.ndarray, f: float, order: int = 2) -> np.ndarray:
    return signal.sosfilt(signal.butter(order, f, btype="low", fs=SR, output="sos"), x)


def _highpass(x: np.ndarray, f: float, order: int = 2) -> np.ndarray:
    return signal.sosfilt(signal.butter(order, f, btype="high", fs=SR, output="sos"), x)


# ------------------------------------------------------------------ one-shot effects

def pop(pitch: float = 880.0, seed: int = 0) -> np.ndarray:
    """Short bubbly 'pop' for small labels: fast downward pitch blip + soft click."""
    t = _t(0.12)
    f = pitch * (0.55 + 0.45 * np.exp(-t * 45))
    tone = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 38)
    click = np.random.default_rng(seed).standard_normal(len(t)) * np.exp(-t * 400) * 0.25
    return _stereo(_norm(tone + _highpass(click, 2000)))


def whoosh(seconds: float = 0.45, rising: bool = True, seed: int = 1) -> np.ndarray:
    """Air whoosh: band-passed noise whose centre sweeps up (or down), swelling to a peak at ~70 %."""
    n = int(seconds * SR)
    rng = np.random.default_rng(seed)
    noise = rng.standard_normal(n)
    out = np.zeros(n)
    blocks = 24
    edges = np.linspace(0, n, blocks + 1).astype(int)
    for i in range(blocks):                       # piecewise sweep of the band centre
        k = i / (blocks - 1)
        c = 350 * (8 ** (k if rising else 1 - k))
        seg = _bandpass(noise[max(edges[i] - 2000, 0):edges[i + 1]], c * 0.6, min(c * 1.7, SR / 2 - 100))
        out[edges[i]:edges[i + 1]] = seg[-(edges[i + 1] - edges[i]):]
    x = np.linspace(0, 1, n)
    env = np.where(x < 0.7, (x / 0.7) ** 2, ((1 - x) / 0.3) ** 1.5)
    y = _norm(out * env)
    left, right = y * np.linspace(1.0, 0.6, n), y * np.linspace(0.6, 1.0, n)   # slight L→R travel
    return np.stack([left, right], axis=1).astype(np.float32)


def ding(pitch: float = 1318.5) -> np.ndarray:
    """Bright bell 'ding' (inharmonic partials, long exponential decay) for numbers / reveals."""
    t = _t(1.0)
    partials = [(1.0, 1.0, 4.0), (2.0, 0.45, 6.0), (2.76, 0.3, 8.0), (5.4, 0.12, 12.0)]
    x = sum(a * np.sin(2 * np.pi * pitch * r * t) * np.exp(-t * d) for r, a, d in partials)
    x *= np.minimum(1, t / 0.003)
    return _stereo(_norm(x))


def impact(seed: int = 2) -> np.ndarray:
    """Low hit for the hook title: sine drop 110→42 Hz + noise transient."""
    t = _t(0.7)
    f = 42 + 68 * np.exp(-t * 18)
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 6)
    hit = _lowpass(np.random.default_rng(seed).standard_normal(len(t)), 2500) * np.exp(-t * 60) * 0.6
    return _stereo(_norm(np.tanh(1.5 * (body + hit))))


EFFECTS = {"pop": pop, "whoosh": whoosh, "ding": ding, "impact": impact}


# ------------------------------------------------------------------ music bed

_NOTE = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def _hz(name: str, octave: int) -> float:
    return 440.0 * 2 ** ((_NOTE[name] + 12 * (octave + 1) - 69) / 12)


def _adsr(n: int, a: float, d: float, s: float, r: float) -> np.ndarray:
    a, d, r = int(a * SR), int(d * SR), int(r * SR)
    env = np.full(n, s, np.float64)
    env[:a] = np.linspace(0, 1, a, endpoint=False)[:n]
    if a < n:
        env[a:a + d] = np.linspace(1, s, d, endpoint=False)[:max(0, min(d, n - a))]
    if r and n > r:
        env[-r:] *= np.linspace(1, 0, r)
    return env


def _reverb(x: np.ndarray, seconds: float = 1.2, mix: float = 0.22, seed: int = 9) -> np.ndarray:
    ir_t = _t(seconds)
    ir = np.random.default_rng(seed).standard_normal(len(ir_t)) * np.exp(-ir_t * 5.5)
    ir = _lowpass(ir, 5000)
    wet = signal.fftconvolve(x, ir)[:len(x)]
    wet *= np.max(np.abs(x)) / (np.max(np.abs(wet)) or 1)
    return x * (1 - mix) + wet * mix


def music_bed(seconds: float, bpm: float = 104.0, seed: int = 4) -> np.ndarray:
    """Original light, upbeat pop/lo-fi loop (I–V–vi–IV in C) for under-dialogue use.
    Bar 1 is a filtered intro; the last 1.5 s fade out. Returns stereo float32 at SR."""
    rng = np.random.default_rng(seed)
    n = int(seconds * SR)
    beat = 60.0 / bpm
    bar = 4 * beat
    chords = [("C", ["C", "E", "G"]), ("G", ["G", "B", "D"]), ("A", ["A", "C", "E"]), ("F", ["F", "A", "C"])]
    pad, pluck, bass, drums = (np.zeros(n) for _ in range(4))
    pluck_r = np.zeros(n)
    n_bars = int(np.ceil(seconds / bar)) + 1
    for b in range(n_bars):
        root, tones = chords[b % 4]
        t0 = b * bar
        i0 = int(t0 * SR)
        if i0 >= n:
            break
        # pad: three detuned saws per chord tone, slow attack
        m = min(int(bar * SR), n - i0)
        tt = np.arange(m) / SR
        chord = np.zeros(m)
        for name in tones:
            f = _hz(name, 4)
            for det in (-0.25, 0.0, 0.3):
                ph = rng.uniform(0, 1)
                chord += signal.sawtooth(2 * np.pi * (f * 2 ** (det / 12)) * tt + ph * 2 * np.pi)
        pad[i0:i0 + m] += chord * _adsr(m, 0.35, 0.3, 0.8, 0.35)
        # pluck arpeggio: 8th notes root-3rd-5th-octave, alternating sides
        arp = [tones[0], tones[1], tones[2], tones[1]] * 2
        for k, name in enumerate(arp):
            s = i0 + int(k * beat / 2 * SR)
            if s >= n:
                break
            L = min(int(0.4 * SR), n - s)
            tk = np.arange(L) / SR
            f = _hz(name, 5 if k % 4 != 3 else 5)
            note = (np.sin(2 * np.pi * f * tk) + 0.35 * np.sin(4 * np.pi * f * tk)) * np.exp(-tk * 9)
            note *= 0.85 if k % 2 else 1.0
            (pluck if k % 2 == 0 else pluck_r)[s:s + L] += note
        # bass: root on 1, the "and" of 2, and 3
        for pos in (0.0, 1.5, 2.0, 3.5):
            s = i0 + int(pos * beat * SR)
            if s >= n:
                break
            L = min(int(beat * 0.9 * SR), n - s)
            tk = np.arange(L) / SR
            f = _hz(root, 2)
            bass[s:s + L] += np.tanh(2 * np.sin(2 * np.pi * f * tk)) * _adsr(L, 0.005, 0.15, 0.6, 0.06)
        # drums (from bar 2): kick 1 & 3 (+ 3.5), clap 2 & 4, hats on 8ths
        if b >= 1:
            for k in range(8):
                s = i0 + int(k * beat / 2 * SR)
                if s >= n:
                    break
                L = min(int(0.3 * SR), n - s)
                tk = np.arange(L) / SR
                if k in (0, 4, 7):
                    fk = 45 + 85 * np.exp(-tk * 30)
                    drums[s:s + L] += np.sin(2 * np.pi * np.cumsum(fk) / SR) * np.exp(-tk * 9) * (0.9 if k == 7 else 1.2)
                if k in (2, 6):
                    nz = _bandpass(rng.standard_normal(L), 1200, 6000)
                    drums[s:s + L] += nz * np.exp(-tk * 22) * 0.9
                hl = min(int(0.05 * SR), n - s)
                hat = _highpass(rng.standard_normal(hl), 7000) * np.exp(-np.arange(hl) / SR * 90)
                drums[s:s + hl] += hat * (0.2 if k % 2 else 0.1)
    pad = _lowpass(pad, 1400) * 0.10
    intro = np.clip(np.arange(n) / SR / bar, 0, 1)                      # bar-1 filter-sweep feel
    pluck_mix = _reverb(pluck * 0.22, mix=0.3)
    pluck_r_mix = _reverb(pluck_r * 0.22, mix=0.3, seed=11)
    bass = _lowpass(bass, 600) * 0.35 * intro
    drums = drums * 0.5
    left = pad + pluck_mix + 0.4 * pluck_r_mix + bass + drums
    right = pad + 0.4 * pluck_mix + pluck_r_mix + bass + drums
    mix = np.stack([left, right], axis=1)
    fade = int(1.5 * SR)
    mix[-fade:] *= np.linspace(1, 0, fade)[:, None]
    mix = np.tanh(mix * 1.2) / np.tanh(1.2)                              # gentle bus saturation
    return _norm(mix, -1.0)


def write_wav(path: str | Path, x: np.ndarray) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    wavfile.write(path, SR, (np.clip(x, -1, 1) * 32767).astype(np.int16))
    return path
