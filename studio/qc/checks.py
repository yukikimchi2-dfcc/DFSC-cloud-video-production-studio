"""Automated quality control for rendered videos.

`run_qc` runs every check that applies and returns a QCReport. Checks that need extra input
(subtitle boxes, overlay boxes, a brand kit) are skipped (status SKIP) when it isn't given.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from ..config import get, load_config
from ..core.io import MediaInfo, probe, read_frames, run_ffmpeg

PASS, WARN, FAIL, SKIP = "PASS", "WARN", "FAIL", "SKIP"


@dataclass
class Check:
    name: str
    status: str
    value: object = None
    expected: object = None
    message: str = ""
    label_zh: str = ""


@dataclass
class QCReport:
    path: str
    checks: list[Check] = field(default_factory=list)
    info: dict = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return all(c.status != FAIL for c in self.checks)

    def by_name(self, name: str) -> Check:
        return next(c for c in self.checks if c.name == name)

    def to_dict(self) -> dict:
        return {"path": self.path, "passed": self.passed, "info": self.info, "checks": [asdict(c) for c in self.checks]}


# ----------------------------------------------------------------------------- individual checks

def check_black_frames(path: str, threshold: float = 0.03, min_duration: float = 0.1,
                       allow_edges: float = 0.0, duration: float | None = None) -> Check:
    """ffmpeg blackdetect. Black at the very start/end within `allow_edges` s is tolerated (fades)."""
    proc = run_ffmpeg(["-hide_banner", "-v", "info", "-i", path, "-vf",
                       f"blackdetect=d={min_duration}:pix_th={threshold}:pic_th=0.98", "-an", "-f", "null", "-"])
    spans = [(float(a), float(b)) for a, b in re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", proc.stderr)]
    dur = duration or 0
    bad = [s for s in spans if not (allow_edges and (s[1] <= allow_edges or (dur and s[0] >= dur - allow_edges)))]
    return Check("black_frames", FAIL if bad else PASS, [list(map(lambda v: round(v, 2), s)) for s in bad], "none",
                 f"{len(bad)} black segment(s)" if bad else "no unexpected black frames", "黑幀檢測")


def check_freeze(path: str, min_seconds: float = 0.5, noise_db: float = -60) -> Check:
    """ffmpeg freezedetect: stuck/frozen picture for >= min_seconds."""
    proc = run_ffmpeg(["-hide_banner", "-v", "info", "-i", path, "-vf",
                       f"freezedetect=n={noise_db}dB:d={min_seconds}", "-an", "-f", "null", "-"])
    starts = [float(v) for v in re.findall(r"freeze_start: ([\d.]+)", proc.stderr)]
    ends = [float(v) for v in re.findall(r"freeze_end: ([\d.]+)", proc.stderr)]
    spans = [[round(s, 2), round(ends[i], 2) if i < len(ends) else None] for i, s in enumerate(starts)]
    return Check("frozen_frames", WARN if spans else PASS, spans, f"< {min_seconds}s",
                 f"{len(spans)} frozen segment(s) — intentional holds are OK, stuck renders are not" if spans
                 else "no frozen segments", "卡幀檢測")


def check_duplicate_frames(path: str, max_run: int = 3, sample_width: int = 64, tolerance: float = 0.6,
                           strict: bool = False) -> Check:
    """Consecutive (near-)identical frames on a 64 px thumbnail: mean absolute difference below
    `tolerance` (0..255 scale, absorbs codec noise). Long runs suggest dropped frames or a stalled
    render; a single dup can be a frame-rate conversion artefact. Held title cards are also static,
    so long runs only FAIL in `strict` mode (e.g. live-action interviews); otherwise WARN."""
    info = probe(path)
    h = max(int(sample_width * info.height / info.width) // 2 * 2, 2)
    prev, run, worst, dups, total = None, 0, 0, 0, 0
    for f in read_frames(path, sample_width, h):
        total += 1
        sig = f.astype(np.float32)
        if prev is not None and float(np.abs(sig - prev).mean()) < tolerance:
            run += 1
            dups += 1
            worst = max(worst, run)
        else:
            run = 0
        prev = sig
    status = (FAIL if strict and worst >= max_run * 3 else WARN) if worst >= max_run else PASS
    return Check("duplicate_frames", status, {"duplicates": dups, "longest_run": worst, "frames": total},
                 f"run < {max_run}", f"{dups} duplicate frame(s), longest run {worst}", "重複幀檢測")


def check_audio_peak(path: str, max_dbfs: float = -1.0) -> Check:
    from ..edit.audio import measure_peak
    peak = measure_peak(path)
    return Check("audio_peak", FAIL if peak > max_dbfs else PASS, round(peak, 2), f"<= {max_dbfs} dBFS",
                 "clipping risk" if peak > max_dbfs else "ok", "音頻峰值")


def check_loudness(path: str, target_lufs: float, tolerance: float, max_tp: float) -> Check:
    from ..edit.audio import measure_loudness
    m = measure_loudness(path, target_lufs, max_tp)
    off = abs(m.integrated_lufs - target_lufs)
    status = PASS if off <= tolerance and m.true_peak_dbtp <= max_tp + 0.2 else (WARN if off <= tolerance * 3 else FAIL)
    return Check("loudness", status, {"lufs": round(m.integrated_lufs, 2), "true_peak": round(m.true_peak_dbtp, 2),
                                      "lra": round(m.lra, 2)},
                 {"lufs": target_lufs, "tolerance": tolerance, "true_peak_max": max_tp},
                 f"{m.integrated_lufs:.1f} LUFS / {m.true_peak_dbtp:.1f} dBTP", "響度 LUFS")


def check_format(info: MediaInfo, expected: dict) -> list[Check]:
    out = []
    if "width" in expected or "height" in expected:
        ok = (info.width, info.height) == (expected.get("width", info.width), expected.get("height", info.height))
        out.append(Check("resolution", PASS if ok else FAIL, f"{info.width}x{info.height}",
                         f"{expected.get('width')}x{expected.get('height')}", "", "解析度"))
    if expected.get("fps"):
        ok = info.fps is not None and abs(info.fps - float(expected["fps"])) < 0.01
        out.append(Check("frame_rate", PASS if ok else FAIL, info.fps and round(info.fps, 3), expected["fps"], "", "幀率"))
    if expected.get("vcodec"):
        out.append(Check("video_codec", PASS if info.vcodec == expected["vcodec"] else FAIL, info.vcodec,
                         expected["vcodec"], "", "影像編碼"))
    if expected.get("pix_fmt"):
        out.append(Check("pixel_format", PASS if info.pix_fmt == expected["pix_fmt"] else FAIL, info.pix_fmt,
                         expected["pix_fmt"], "yuv420p is required for social platforms", "像素格式"))
    if expected.get("acodec"):
        out.append(Check("audio_codec", PASS if info.acodec == expected["acodec"] else FAIL, info.acodec,
                         expected["acodec"], "", "音訊編碼"))
    if expected.get("duration"):
        tol = expected.get("duration_tolerance", 0.1)
        ok = abs(info.duration - expected["duration"]) <= tol
        out.append(Check("duration", PASS if ok else FAIL, round(info.duration, 3), expected["duration"], "", "片長"))
    if expected.get("max_size_mb"):
        mb = info.size_bytes / 1e6
        out.append(Check("file_size", PASS if mb <= expected["max_size_mb"] else WARN, round(mb, 2),
                         f"<= {expected['max_size_mb']} MB", "", "檔案大小"))
    return out


def _safe_rect(w: int, h: int, safe: dict) -> tuple[float, float, float, float]:
    return (w * safe.get("left", 0), h * safe.get("top", 0), w * (1 - safe.get("right", 0)), h * (1 - safe.get("bottom", 0)))


def check_subtitle_safe_area(boxes: list[tuple], width: int, height: int, safe: dict) -> Check:
    """boxes: [(t, x0, y0, x1, y1)] in output pixels (e.g. collected from SubtitleLayer.last_box)."""
    sx0, sy0, sx1, sy1 = _safe_rect(width, height, safe)
    bad = [b for b in boxes if b[1] < sx0 - 1 or b[2] < sy0 - 1 or b[3] > sx1 + 1 or b[4] > sy1 + 1]
    return Check("subtitle_safe_area", FAIL if bad else PASS, {"violations": len(bad), "first": bad[:3]},
                 "inside safe area", f"{len(bad)}/{len(boxes)} subtitle boxes outside safe area", "字幕越界")


def check_fonts(brand) -> Check:
    problems = brand.check_fonts()
    return Check("fonts", FAIL if problems else PASS, problems, "all font files present",
                 "; ".join(problems) or "ok", "字體缺失")


def check_face_occlusion(face_boxes: list[tuple], overlay_boxes: list[tuple], max_overlap: float = 0.15) -> Check:
    """face_boxes / overlay_boxes: [(t, x0, y0, x1, y1)]. Fails when an overlay active at the same
    time covers more than `max_overlap` of a face."""
    worst, hits = 0.0, []
    for ft, fx0, fy0, fx1, fy1 in face_boxes:
        farea = max((fx1 - fx0) * (fy1 - fy0), 1)
        for ot, ox0, oy0, ox1, oy1 in overlay_boxes:
            if abs(ot - ft) > 1e-3:
                continue
            iw, ih = max(min(fx1, ox1) - max(fx0, ox0), 0), max(min(fy1, oy1) - max(fy0, oy0), 0)
            frac = iw * ih / farea
            worst = max(worst, frac)
            if frac > max_overlap:
                hits.append(round(ft, 2))
    return Check("face_occlusion", FAIL if hits else PASS, {"worst_overlap": round(worst, 3), "times": hits[:10]},
                 f"<= {max_overlap:.0%}", f"{len(hits)} occlusion(s)" if hits else "faces clear", "人臉遮擋")


def detect_face_boxes(path: str, every: float = 1.0) -> list[tuple]:
    """Sample faces in a rendered video as [(t, x0, y0, x1, y1)] (output pixels)."""
    from ..edit.reframe import detect_faces
    out = []
    for i, f in enumerate(read_frames(path, fps=1 / every)):
        for x, y, w, h in detect_faces(f):
            out.append((i * every, x, y, x + w, y + h))
    return out


# ----------------------------------------------------------------------------- orchestration

def run_qc(video_path: str | Path, cfg: dict | None = None, expected: dict | None = None, brand=None,
           subtitle_boxes: list[tuple] | None = None, overlay_boxes: list[tuple] | None = None,
           face_boxes: list[tuple] | None = None, loudness_target: float | None = None,
           allow_black_edges: float = 0.5, strict_motion: bool = False) -> QCReport:
    """Run all applicable checks. `expected` may hold width/height/fps/vcodec/pix_fmt/acodec/duration/max_size_mb.
    `strict_motion=True` turns long duplicate-frame runs into failures (footage that should never hold still)."""
    cfg = cfg or load_config()
    path = str(video_path)
    info = probe(path)
    report = QCReport(path, info={k: v for k, v in info.__dict__.items()})
    expected = {"vcodec": "h264", "pix_fmt": get(cfg, "render.pix_fmt", "yuv420p"), **(expected or {})}
    report.checks += check_format(info, expected)
    if info.has_video:
        report.checks.append(check_black_frames(path, get(cfg, "qc.black_frame_threshold", 0.03),
                                                allow_edges=allow_black_edges, duration=info.duration))
        report.checks.append(check_freeze(path, get(cfg, "qc.freeze_min_seconds", 0.5)))
        report.checks.append(check_duplicate_frames(path, strict=strict_motion))
    if info.has_audio:
        report.checks.append(check_audio_peak(path, get(cfg, "qc.peak_dbfs_max", -1.0)))
        if loudness_target is not None:
            report.checks.append(check_loudness(path, loudness_target, get(cfg, "qc.lufs_tolerance", 1.0),
                                                get(cfg, "render.final.true_peak_dbtp", -1.5)))
    else:
        report.checks.append(Check("audio_present", WARN, False, True, "no audio stream", "音訊"))
    safe = get(cfg, "safe_area", {})
    if subtitle_boxes is not None and info.has_video:
        report.checks.append(check_subtitle_safe_area(subtitle_boxes, info.width, info.height, safe))
    else:
        report.checks.append(Check("subtitle_safe_area", SKIP, message="no subtitle boxes supplied", label_zh="字幕越界"))
    report.checks.append(check_fonts(brand) if brand is not None else
                         Check("fonts", SKIP, message="no brand supplied", label_zh="字體缺失"))
    if overlay_boxes is not None and info.has_video:
        faces = face_boxes if face_boxes is not None else detect_face_boxes(path)
        report.checks.append(check_face_occlusion(faces, overlay_boxes))
    else:
        report.checks.append(Check("face_occlusion", SKIP, message="no overlay boxes supplied", label_zh="人臉遮擋"))
    return report
