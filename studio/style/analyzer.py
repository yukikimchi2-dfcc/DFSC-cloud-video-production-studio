"""Video Style Intelligence: measure the editing / visual / audio style of a reference video.

Everything here is *measured* (shot lengths, motion, colour, text placement, tempo ...).
Creative judgements (narrative, taste, why it works) are listed as open questions in the
report for a human reviewer — the analyzer never decides that a style is "good".
"""
from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
from scipy import signal

from ..core.io import probe, read_audio, read_frames


# ----------------------------------------------------------------------------- shots

def _hist(frame: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(frame, cv2.COLOR_RGB2HSV)
    h = cv2.calcHist([hsv], [0, 1, 2], None, [16, 8, 8], [0, 180, 0, 256, 0, 256])
    return cv2.normalize(h, h).flatten()


def detect_shots(diffs: np.ndarray, times: np.ndarray, threshold: float = 0.35, min_gap: float = 0.25) -> list[float]:
    """Cut times from per-sample histogram distances (Bhattacharyya). A cut must exceed `threshold`
    and stand out from its neighbourhood (adaptive) so fast motion isn't mistaken for a cut."""
    cuts: list[float] = []
    for i in range(1, len(diffs)):
        lo, hi = max(i - 5, 1), min(i + 6, len(diffs))
        local = np.median(diffs[lo:hi])
        if diffs[i] > threshold and diffs[i] > 2.5 * local + 0.05 and (not cuts or times[i] - cuts[-1] >= min_gap):
            cuts.append(float(times[i]))
    return cuts


# ----------------------------------------------------------------------------- motion

def camera_motion(prev_gray: np.ndarray, gray: np.ndarray) -> tuple[float, float, float]:
    """Global (dx, dy, zoom) between two frames from dense optical flow.
    dx/dy in fractions of frame width per frame; zoom = mean radial flow (positive = push in)."""
    flow = cv2.calcOpticalFlowFarneback(prev_gray, gray, None, 0.5, 3, 15, 3, 5, 1.2, 0)
    h, w = gray.shape
    dx, dy = float(np.median(flow[..., 0])), float(np.median(flow[..., 1]))
    ys, xs = np.mgrid[0:h, 0:w]
    rx, ry = xs - w / 2, ys - h / 2
    r = np.sqrt(rx ** 2 + ry ** 2) + 1e-6
    radial = ((flow[..., 0] - dx) * rx + (flow[..., 1] - dy) * ry) / r
    return dx / w, dy / w, float(np.median(radial)) / (w / 2)


# ----------------------------------------------------------------------------- text regions

def text_regions(frame: np.ndarray) -> list[tuple[float, float, float, float]]:
    """Heuristic caption/title boxes (x, y, w, h as frame fractions).

    Targets the dominant social-video text styles: light text with a dark outline/shadow and dark
    text on a light card. Pixels qualify when a near-white pixel touches a near-black one (or vice
    versa); qualifying pixels are joined horizontally into lines and filtered by size, aspect and
    stroke density. Busy graphics can still produce false positives — treat results as estimates."""
    h, w = frame.shape[:2]
    gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
    sat = cv2.cvtColor(frame, cv2.COLOR_RGB2HSV)[..., 1]
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    light = ((gray > 200) & (sat < 60)).astype(np.uint8)
    dark = (gray < 60).astype(np.uint8)
    edge = (light & cv2.dilate(dark, k, iterations=2)) | (dark & cv2.dilate(light, k, iterations=2))
    joined = cv2.morphologyEx(edge * 255, cv2.MORPH_CLOSE,
                              cv2.getStructuringElement(cv2.MORPH_RECT, (max(w // 25, 3), max(h // 120, 1))))
    contours, _ = cv2.findContours(joined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    out = []
    for c in contours:
        x, y, cw, ch = cv2.boundingRect(c)
        if not (0.02 * h <= ch <= 0.15 * h) or cw < 1.5 * ch or cw > 0.95 * w:
            continue
        density = float(edge[y:y + ch, x:x + cw].mean())
        # characters produce many light/dark transitions along a row; flat graphic edges don't
        row = edge[y + ch // 2, x:x + cw].astype(np.int8)
        transitions = int(np.abs(np.diff(row)).sum()) / max(cw / ch, 1)
        if 0.05 <= density <= 0.6 and transitions >= 3:
            out.append((x / w, y / h, cw / w, ch / h))
    return out


# ----------------------------------------------------------------------------- colour

def palette(frames: list[np.ndarray], k: int = 5) -> list[dict]:
    px = np.concatenate([cv2.resize(f, (48, int(48 * f.shape[0] / f.shape[1]) or 1)).reshape(-1, 3) for f in frames])
    px = px.astype(np.float32)
    k = min(k, len(np.unique(px, axis=0)))
    _, labels, centers = cv2.kmeans(px, k, None, (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.5),
                                    3, cv2.KMEANS_PP_CENTERS)
    counts = np.bincount(labels.flatten(), minlength=k) / len(labels)
    order = np.argsort(-counts)
    return [{"hex": "#" + "".join(f"{int(round(v)):02X}" for v in centers[i]), "share": round(float(counts[i]), 3)}
            for i in order]


def colour_stats(frames: list[np.ndarray]) -> dict:
    lum, sat, con = [], [], []
    for f in frames:
        hsv = cv2.cvtColor(f, cv2.COLOR_RGB2HSV)
        y = cv2.cvtColor(f, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255
        lum.append(float(y.mean()))
        con.append(float(y.std()))
        sat.append(float(hsv[..., 1].mean() / 255))
    return {"brightness": round(float(np.mean(lum)), 3), "contrast": round(float(np.mean(con)), 3),
            "saturation": round(float(np.mean(sat)), 3), "brightness_range": [round(min(lum), 3), round(max(lum), 3)]}


# ----------------------------------------------------------------------------- audio

def audio_rhythm(path: str | Path, sr: int = 22050) -> dict:
    """Tempo (BPM) by autocorrelation of a spectral-flux onset envelope, plus onset density."""
    audio = read_audio(path, sr, mono=True)[:, 0]
    if len(audio) < sr:
        return {"bpm": None, "onsets_per_sec": 0.0, "rms_db": None}
    _, _, z = signal.stft(audio, sr, nperseg=1024, noverlap=1024 - 512)
    mag = np.log1p(np.abs(z))
    flux = np.maximum(np.diff(mag, axis=1), 0).sum(axis=0)
    flux = (flux - flux.mean()) / (flux.std() + 1e-9)
    hop_t = 512 / sr
    peaks, _ = signal.find_peaks(flux, height=1.0, distance=max(int(0.1 / hop_t), 1))
    ac = signal.correlate(flux, flux, mode="full")[len(flux) - 1:]
    ac = np.convolve(ac, np.ones(3), "same")   # a beat period rarely lands on one hop; merge split peaks
    lags = np.arange(len(ac)) * hop_t
    valid = (lags >= 60 / 180) & (lags <= 60 / 60)
    bpm = None
    if valid.any() and ac[valid].max() > 0.1 * ac[0]:
        # every multiple of the beat period correlates too; take the shortest lag that is nearly as
        # strong as the best one to avoid half-tempo (octave) errors
        cand, _ = signal.find_peaks(ac[valid])
        vlags, vac = lags[valid], ac[valid]
        strong = [i for i in cand if vac[i] >= 0.8 * vac.max()] or [int(np.argmax(vac))]
        bpm = round(float(60 / vlags[min(strong)]), 1)
    rms = float(np.sqrt(np.mean(audio ** 2)))
    return {"bpm": bpm, "onsets_per_sec": round(len(peaks) / (len(audio) / sr), 2),
            "rms_db": round(float(20 * np.log10(rms + 1e-9)), 1)}


# ----------------------------------------------------------------------------- main

def analyze_video(path: str | Path, sample_fps: float = 8.0, width: int = 320, hook_seconds: float = 3.0,
                  keyframe_limit: int = 12) -> dict:
    """Measure a video's style. Returns a JSON-serialisable dict (keyframes kept as arrays under '_keyframes')."""
    info = probe(path)
    h = int(width * info.height / info.width) // 2 * 2
    times, diffs, motions, text_hits, sampled = [], [], [], [], []
    prev_h = prev_g = None
    for i, f in enumerate(read_frames(path, width, h, fps=sample_fps)):
        t = i / sample_fps
        g = cv2.cvtColor(f, cv2.COLOR_RGB2GRAY)
        hist = _hist(f)
        diffs.append(0.0 if prev_h is None else float(cv2.compareHist(prev_h, hist, cv2.HISTCMP_BHATTACHARYYA)))
        motions.append((0.0, 0.0, 0.0) if prev_g is None else camera_motion(prev_g, g))
        text_hits.append(text_regions(f))
        times.append(t)
        sampled.append(f)
        prev_h, prev_g = hist, g
    times_a, diffs_a = np.array(times), np.array(diffs)
    cuts = detect_shots(diffs_a, times_a)
    dur = info.duration or (len(times) / sample_fps)
    bounds = [0.0, *cuts, dur]
    shots = [{"start": round(a, 3), "end": round(b, 3), "duration": round(b - a, 3)} for a, b in zip(bounds, bounds[1:])]
    cut_set = set(cuts)
    # motion only within shots (ignore the sample pair spanning a cut)
    m = np.array([mv for t, mv in zip(times, motions) if t not in cut_set]) if motions else np.zeros((1, 3))
    per_sec = sample_fps
    motion = {"pan_speed": round(float(np.mean(np.abs(m[:, 0]))) * per_sec, 4),
              "tilt_speed": round(float(np.mean(np.abs(m[:, 1]))) * per_sec, 4),
              "zoom_speed": round(float(np.mean(m[:, 2])) * per_sec, 4),
              "shake": round(float(np.std(m[:, 0]) + np.std(m[:, 1])) * per_sec, 4),
              "unit": "fraction of frame width per second (zoom: radial, + = push in)"}
    # pacing curve: cuts per 5 s window
    win = 5.0
    pacing = [sum(1 for c in cuts if k * win <= c < (k + 1) * win) for k in range(int(np.ceil(dur / win)) or 1)]
    # text
    frames_with_text = [boxes for boxes in text_hits if boxes]
    all_boxes = [b for boxes in text_hits for b in boxes]
    text = {"frames_with_text_ratio": round(len(frames_with_text) / max(len(text_hits), 1), 3)}
    if all_boxes:
        ys = np.array([b[1] + b[3] / 2 for b in all_boxes])
        hs = np.array([b[3] for b in all_boxes])
        text.update({"median_center_y": round(float(np.median(ys)), 3), "median_height": round(float(np.median(hs)), 4),
                     "zone": "bottom" if np.median(ys) > 0.66 else "top" if np.median(ys) < 0.33 else "middle"})
    # hook
    hook_idx = [i for i, t in enumerate(times) if t < hook_seconds]
    hook = {"seconds": hook_seconds, "cuts": sum(1 for c in cuts if c < hook_seconds),
            "motion": round(float(np.mean([abs(motions[i][0]) + abs(motions[i][1]) + abs(motions[i][2])
                                           for i in hook_idx])) * per_sec, 4) if hook_idx else 0.0,
            "text_ratio": round(sum(1 for i in hook_idx if text_hits[i]) / max(len(hook_idx), 1), 3)}
    # keyframes: middle of each shot (evenly thinned)
    mids = [(s["start"] + s["end"]) / 2 for s in shots]
    if len(mids) > keyframe_limit:
        mids = [mids[int(i)] for i in np.linspace(0, len(mids) - 1, keyframe_limit)]
    keyframes = [(round(t, 2), sampled[min(int(t * sample_fps), len(sampled) - 1)]) for t in mids] if sampled else []
    colour_frames = sampled[::max(len(sampled) // 40, 1)]
    lens = np.array([s["duration"] for s in shots])
    result = {
        "source": str(path),
        "format": {"width": info.width, "height": info.height, "fps": info.fps, "duration": round(dur, 3),
                   "aspect": round(info.width / info.height, 4) if info.height else None},
        "editing": {"shots": len(shots), "average_shot_length": round(float(lens.mean()), 3),
                    "median_shot_length": round(float(np.median(lens)), 3),
                    "shortest_shot": round(float(lens.min()), 3), "longest_shot": round(float(lens.max()), 3),
                    "cuts_per_minute": round(len(cuts) / dur * 60, 2) if dur else 0.0,
                    "cut_times": [round(c, 3) for c in cuts], "pacing_cuts_per_5s": pacing},
        "hook": hook,
        "camera_motion": motion,
        "text": text,
        "colour": {**colour_stats(colour_frames), "palette": palette(colour_frames)} if colour_frames else {},
        "structure": {"intro_shot": shots[0] if shots else None, "outro_shot": shots[-1] if shots else None,
                      "opens_dark": bool(colour_frames and colour_stats(sampled[:2])["brightness"] < 0.08),
                      "ends_dark": bool(colour_frames and colour_stats(sampled[-2:])["brightness"] < 0.08),
                      "outro_has_text": bool(text_hits and any(text_hits[-int(sample_fps * 2):]))},
        "audio": {},
        "_keyframes": keyframes,
    }
    if info.has_audio:
        result["audio"] = audio_rhythm(path)
        try:
            from ..edit.audio import measure_loudness
            ld = measure_loudness(path)
            result["audio"].update({"integrated_lufs": round(ld.integrated_lufs, 2), "true_peak": round(ld.true_peak_dbtp, 2)})
        except Exception as e:  # pragma: no cover - silent tracks etc.
            result["audio"]["loudness_error"] = str(e)
    return result


HUMAN_QUESTIONS = [
    "敘事結構：開場三秒用了什麼鉤子（問題、衝突、驚人數字、畫面）？ Narrative hook — what grabs attention?",
    "情緒曲線：影片的情緒如何起伏，音樂與剪輯是否配合？ Emotional arc and music/edit sync",
    "字幕與字卡的語氣、用字風格是否符合品牌？ Copy tone of captions / title cards",
    "轉場與 Motion Graphics 的設計語言（簡約 / 活潑 / 高級感）？ Motion design language",
    "CTA 呈現方式是否清楚、有說服力？ CTA clarity",
    "這支影片是否為已核准作品？應標記為 APPROVED / REFERENCE_ONLY / REJECTED？ Review status",
]


def write_style_report(analysis: dict, out_dir: str | Path, stem: str | None = None) -> tuple[Path, Path]:
    """Write <stem>_style.md, <stem>_style.json and keyframe JPEGs. Returns (md, json)."""
    out = Path(out_dir)
    stem = stem or Path(analysis["source"]).stem
    kf_dir = out / f"{stem}_keyframes"
    kf_dir.mkdir(parents=True, exist_ok=True)
    kf_files = []
    for t, img in analysis.get("_keyframes", []):
        p = kf_dir / f"kf_{t:07.2f}s.jpg"
        cv2.imwrite(str(p), cv2.cvtColor(img, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 85])
        kf_files.append((t, p))
    data = {k: v for k, v in analysis.items() if not k.startswith("_")}
    data["keyframes"] = [{"t": t, "file": str(p.relative_to(out))} for t, p in kf_files]
    js = out / f"{stem}_style.json"
    js.write_text(json.dumps(data, ensure_ascii=False, indent=1, default=float), encoding="utf-8")

    e, hook, cm, tx, col, au, st = (data["editing"], data["hook"], data["camera_motion"], data["text"],
                                    data.get("colour", {}), data.get("audio", {}), data["structure"])
    pal = " ".join(f"`{p['hex']}` {p['share']:.0%}" for p in col.get("palette", []))
    md = [
        f"# 風格分析報告 Style Analysis — {Path(data['source']).name}",
        "",
        "> 審核狀態 Review status: **UNREVIEWED** — 以下數據為自動量測，不代表此風格已獲認可。",
        "",
        "## A. 自動量測 Measured metrics",
        "",
        f"- 規格 Format: {data['format']['width']}x{data['format']['height']} · {round(data['format']['fps'] or 0, 2)} fps · {data['format']['duration']} s",
        f"- 鏡頭數 Shots: {e['shots']} · 平均鏡頭長度 ASL {e['average_shot_length']} s (median {e['median_shot_length']} s, "
        f"min {e['shortest_shot']} / max {e['longest_shot']})",
        f"- 剪輯頻率 Cuts per minute: {e['cuts_per_minute']}",
        f"- 節奏曲線 Pacing (cuts / 5 s): {e['pacing_cuts_per_5s']}",
        f"- 前 {hook['seconds']:.0f} 秒 Hook: cuts {hook['cuts']} · motion {hook['motion']} · text on screen {hook['text_ratio']:.0%}",
        f"- 運鏡 Camera motion: pan {cm['pan_speed']} · tilt {cm['tilt_speed']} · zoom {cm['zoom_speed']} · shake {cm['shake']} ({cm['unit']})",
        f"- 字幕/文字 Text: on screen {tx['frames_with_text_ratio']:.0%} of samples"
        + (f" · zone {tx['zone']} · centre y {tx['median_center_y']} · height {tx['median_height']} of frame" if "zone" in tx else ""),
        f"- 色彩 Colour: brightness {col.get('brightness')} · contrast {col.get('contrast')} · saturation {col.get('saturation')}",
        f"- 主色 Palette: {pal}",
        f"- 音樂/音訊 Audio: BPM {au.get('bpm')} · onsets/s {au.get('onsets_per_sec')} · LUFS {au.get('integrated_lufs')} · TP {au.get('true_peak')}",
        f"- 片頭 Intro shot: {st['intro_shot']} · opens dark: {st['opens_dark']}",
        f"- 片尾 Outro shot: {st['outro_shot']} · ends dark: {st['ends_dark']} · outro has text: {st['outro_has_text']}",
        "",
        "量測說明：鏡頭切點使用色彩直方圖差異；運鏡由光流估算；文字區域為啟發式偵測（可能把高對比圖形誤判為文字）；BPM 為自相關估算。",
        "",
        "## B. 關鍵畫面 Keyframes",
        "",
        *[f"- {t:.2f}s — ![]({p.relative_to(out)})" for t, p in kf_files],
        "",
        "## C. 需要人工判斷 Needs human judgement",
        "",
        *[f"- [ ] {q}" for q in HUMAN_QUESTIONS],
        "",
    ]
    mdp = out / f"{stem}_style.md"
    mdp.write_text("\n".join(md), encoding="utf-8")
    return mdp, js
