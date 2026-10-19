"""Easing curves. Every function maps t in [0, 1] -> progress (may overshoot for back/elastic)."""
from __future__ import annotations

import math
from typing import Callable

Easing = Callable[[float], float]


def clamp01(t: float) -> float:
    return 0.0 if t < 0 else 1.0 if t > 1 else t


def linear(t): return t
def in_quad(t): return t * t
def out_quad(t): return 1 - (1 - t) ** 2
def in_out_quad(t): return 2 * t * t if t < 0.5 else 1 - (-2 * t + 2) ** 2 / 2
def in_cubic(t): return t ** 3
def out_cubic(t): return 1 - (1 - t) ** 3
def in_out_cubic(t): return 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2
def out_quart(t): return 1 - (1 - t) ** 4
def out_expo(t): return 1.0 if t >= 1 else 1 - 2 ** (-10 * t)
def in_out_expo(t):
    if t <= 0 or t >= 1:
        return float(t >= 1)
    return 2 ** (20 * t - 10) / 2 if t < 0.5 else (2 - 2 ** (-20 * t + 10)) / 2
def in_out_sine(t): return -(math.cos(math.pi * t) - 1) / 2


def out_back(t, s: float = 1.70158):
    return 1 + (s + 1) * (t - 1) ** 3 + s * (t - 1) ** 2


def out_elastic(t):
    if t <= 0 or t >= 1:
        return float(t >= 1)
    c4 = (2 * math.pi) / 3
    return 2 ** (-10 * t) * math.sin((t * 10 - 0.75) * c4) + 1


def out_bounce(t):
    n1, d1 = 7.5625, 2.75
    if t < 1 / d1:
        return n1 * t * t
    if t < 2 / d1:
        t -= 1.5 / d1
        return n1 * t * t + 0.75
    if t < 2.5 / d1:
        t -= 2.25 / d1
        return n1 * t * t + 0.9375
    t -= 2.625 / d1
    return n1 * t * t + 0.984375


EASINGS: dict[str, Easing] = {
    name: fn for name, fn in globals().items()
    if callable(fn) and (name == "linear" or name.startswith(("in_", "out_")))
}


def get(name: str | Easing) -> Easing:
    if callable(name):
        return name
    try:
        return EASINGS[name]
    except KeyError as e:
        raise ValueError(f"Unknown easing '{name}'. Available: {sorted(EASINGS)}") from e


def progress(t: float, start: float, duration: float, easing: str | Easing = "linear") -> float:
    """Eased progress of an animation that starts at `start` and lasts `duration` seconds."""
    if duration <= 0:
        return 1.0 if t >= start else 0.0
    return get(easing)(clamp01((t - start) / duration))


def lerp(a: float, b: float, p: float) -> float:
    return a + (b - a) * p
