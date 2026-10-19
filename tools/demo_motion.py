#!/usr/bin/env python3
"""Render a ~8 s synthetic TEST reel that exercises the motion engine, or regenerate template previews.

    python tools/demo_motion.py OUT_DIR [--width 540 --height 960]
    python tools/demo_motion.py --previews          # rewrite templates/*/preview.{png,gif} + test_record.json

Everything on screen is generated — no real footage — and the reel is watermarked "TEST · 合成測試素材".
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from studio.brand import load_brand  # noqa: E402
from studio.core.timeline import Timeline  # noqa: E402
from studio.motion import cards, particles  # noqa: E402
from studio.motion.camera import CameraShake, HandheldDrift, Pan  # noqa: E402
from studio.motion.stickers import StickerLayer  # noqa: E402
from studio.motion.templates import build_template, list_templates, render_template_preview, synthetic_background  # noqa: E402
from studio.motion.transitions import GroupLayer, SequenceLayer, Transition  # noqa: E402
from studio.motion.typography import TextLayer, WordHighlightLayer  # noqa: E402
from studio.versioning import reserve_output  # noqa: E402

FPS = 30


def build_demo(brand) -> Timeline:
    seg1 = GroupLayer([
        synthetic_background(1), HandheldDrift(amplitude=0.02, z=-50),
        *build_template("title_card_impact", {"text": "啟航 北極星", "subtitle": "Typography · Cards · Camera"}, brand),
        StickerLayer("🚀", x=840, y=470, height=200, start=0.6, z=20),
    ], duration=3.0)
    seg2 = GroupLayer([
        synthetic_background(2), Pan(start_center=(0.3, 0.5), end_center=(0.7, 0.5), zoom=1.3, duration=2.8, z=-50),
        particles.LightDots(count=24, z=-10),
        *build_template("lower_third_basic", {"name": "測試人物", "title": "合成素材 · 非正式影片"}, brand),
        TextLayer("逐字動畫 Bounce", y=380, size=100, animation="bounce", stagger=0.06, stroke=6, z=12,
                  underline={"color": "secondary"}),
        StickerLayer("✨", x=200, y=820, height=150, enter="fly_left", start=0.4, z=20),
    ], duration=2.8)
    seg3 = GroupLayer([
        *build_template("stat_counter", {"value": 2027, "label": "Find Your North Star", "suffix": "", "y": 520,
                                         "color": "blue", "panel_opacity": 1.0}, brand),
        WordHighlightLayer([{"text": w, "start": i * 0.32, "end": (i + 1) * 0.32}
                            for i, w in enumerate(["動態", "字幕", "逐字", "高亮", "測試"])], y=1260, z=20),
        particles.ParticleEmitter(origin=(540, 760), burst=60, rate=0, lifetime=1.5, gravity=200,
                                  colors=["#FFFFFF", "blue"], start=1.2, duration=1.6, z=15),
        CameraShake(intensity=0.01, start=1.2, duration=0.6, z=10),
        particles.Vignette(strength=0.3, z=30),
    ], background=brand.color("green"), duration=2.8)
    seq = SequenceLayer([seg1, seg2, seg3], [Transition("whip_pan", 8), Transition("star", 16)], fps=FPS)
    tl = Timeline(1080, 1920, fps=FPS, duration=seq.duration, brand=brand)
    tl.add(seq)
    tl.add(TextLayer("TEST · 合成測試素材", x=540, y=60, size=40, role="body", color="#FFFFFF", animation="none",
                     safe_clamp=False, shadow={"blur": 4, "opacity": 0.6}, z=1000, opacity=0.85))
    tl.add(particles.ChromaticAberration(amount=2, z=999))
    return tl


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out_dir", nargs="?")
    ap.add_argument("--width", type=int, default=540)
    ap.add_argument("--height", type=int, default=960)
    ap.add_argument("--project", default="dfsc-2027")
    ap.add_argument("--previews", action="store_true", help="regenerate every template preview instead")
    args = ap.parse_args()

    if args.previews:
        for meta in list_templates():
            r = render_template_preview(meta["id"])
            print(f"{meta['id']:28s} gif={r['record']['gif_bytes'] / 1e6:.2f}MB passed={r['record']['passed']}")
        return 0
    if not args.out_dir:
        ap.error("out_dir is required unless --previews")

    tl = build_demo(load_brand(args.project))
    out = reserve_output(args.out_dir, "motion_demo", "test")
    t0 = time.time()
    tl.render(out, width=args.width, height=args.height, crf=23, preset="veryfast",
              progress=lambda i, n: print(f"\rframe {i}/{n}", end="", flush=True) if i % 30 == 0 or i == n else None)
    print(f"\nwrote {out} ({tl.duration:.1f}s, {time.time() - t0:.1f}s render)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
