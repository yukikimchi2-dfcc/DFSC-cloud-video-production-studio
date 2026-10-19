#!/usr/bin/env python3
"""Extract vector brand assets from a PDF-compatible Adobe Illustrator (.ai) file.

Writes, for each named group of drawing indices:
  <out>/<name>.json   flattened polygons for studio.core.vector.render_shape
  <out>/<name>.svg    the same geometry as SVG (for designers / Drive)
  <out>/<name>.png    transparent preview, longest side 1024 px
plus <out>/key_visual_preview.png (whole artboard) and <out>/palette.json (fill colours found).

Usage:
  python tools/extract_ai_assets.py SOURCE.ai OUT_DIR --groups groups.yaml
groups.yaml maps a name to drawing indices, e.g. {north_star_tricolor: [28, 29, 30, 31]}.
Run with --list to print every drawing with its index, colour and bounds.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pymupdf
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from studio.core import vector  # noqa: E402
from studio.core.canvas import to_uint8  # noqa: E402


def _hex(rgb) -> str:
    return "#" + "".join(f"{round(c * 255):02X}" for c in rgb)


def drawing_subpaths(drawing) -> list[list[tuple[float, float]]]:
    """Flatten a PyMuPDF drawing into closed polygons. A new subpath starts on every move."""
    subpaths: list[list[tuple[float, float]]] = []
    cur: list[tuple[float, float]] = []
    for item in drawing["items"]:
        kind = item[0]
        if kind == "l":
            p0, p1 = item[1], item[2]
            if not cur or (abs(cur[-1][0] - p0.x) > 1e-3 or abs(cur[-1][1] - p0.y) > 1e-3):
                if len(cur) >= 3:
                    subpaths.append(cur)
                cur = [(p0.x, p0.y)]
            cur.append((p1.x, p1.y))
        elif kind == "c":
            p0, p1, p2, p3 = (np.array([p.x, p.y]) for p in item[1:5])
            if not cur or np.hypot(cur[-1][0] - p0[0], cur[-1][1] - p0[1]) > 1e-3:
                if len(cur) >= 3:
                    subpaths.append(cur)
                cur = [tuple(p0)]
            cur.extend(vector.flatten_cubic(p0, p1, p2, p3))
        elif kind == "re":
            r = item[1]
            if len(cur) >= 3:
                subpaths.append(cur)
            subpaths.append([(r.x0, r.y0), (r.x1, r.y0), (r.x1, r.y1), (r.x0, r.y1)])
            cur = []
        elif kind == "qu":
            q = item[1]
            if len(cur) >= 3:
                subpaths.append(cur)
            subpaths.append([(q.ul.x, q.ul.y), (q.ur.x, q.ur.y), (q.lr.x, q.lr.y), (q.ll.x, q.ll.y)])
            cur = []
    if len(cur) >= 3:
        subpaths.append(cur)
    return subpaths


def build_shape(drawings, indices: list[int]) -> dict:
    paths = []
    for i in indices:
        d = drawings[i]
        if not d.get("fill"):
            continue
        paths.append({"fill": _hex(d["fill"]), "subpaths": drawing_subpaths(d)})
    pts = np.concatenate([np.asarray(sp) for p in paths for sp in p["subpaths"]])
    x0, y0 = pts.min(0)
    x1, y1 = pts.max(0)
    for p in paths:
        p["subpaths"] = [[[round(float(x - x0), 3), round(float(y - y0), 3)] for x, y in sp] for sp in p["subpaths"]]
    return {"viewbox": [round(float(x1 - x0), 3), round(float(y1 - y0), 3)], "paths": paths}


def shape_to_svg(shape: dict) -> str:
    w, h = shape["viewbox"]
    body = []
    for p in shape["paths"]:
        d = " ".join("M" + " L".join(f"{x},{y}" for x, y in sp) + " Z" for sp in p["subpaths"])
        body.append(f'  <path fill="{p["fill"]}" fill-rule="evenodd" d="{d}"/>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">\n'
            + "\n".join(body) + "\n</svg>\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source")
    ap.add_argument("out_dir", nargs="?")
    ap.add_argument("--groups", help="YAML mapping name -> list of drawing indices")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--page", type=int, default=0)
    args = ap.parse_args()

    doc = pymupdf.open(args.source)
    page = doc[args.page]
    drawings = page.get_drawings()
    if args.list:
        for i, d in enumerate(drawings):
            fill = _hex(d["fill"]) if d.get("fill") else None
            print(i, d["type"], fill, [round(v) for v in d["rect"]], len(d["items"]), d.get("layer"))
        return 0
    if not (args.out_dir and args.groups):
        ap.error("out_dir and --groups are required unless --list")

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    groups = yaml.safe_load(Path(args.groups).read_text(encoding="utf-8"))
    for name, indices in groups.items():
        shape = build_shape(drawings, indices)
        (out / f"{name}.json").write_text(json.dumps(shape, separators=(",", ":")), encoding="utf-8")
        (out / f"{name}.svg").write_text(shape_to_svg(shape), encoding="utf-8")
        vw, vh = shape["viewbox"]
        patch = vector.render_shape(shape, int(1024 * min(1.0, vh / vw)))  # longest side 1024 px
        from PIL import Image
        Image.fromarray(to_uint8(patch.rgba), "RGBA").save(out / f"{name}.png")
        print(f"wrote {name}: viewbox={shape['viewbox']} paths={len(shape['paths'])}")

    page.get_pixmap(dpi=144).save(out / "key_visual_preview.png")
    palette = Counter(_hex(d["fill"]) for d in drawings if d.get("fill"))
    (out / "palette.json").write_text(json.dumps(palette.most_common(), indent=2), encoding="utf-8")
    print("palette:", palette.most_common())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
