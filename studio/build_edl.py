"""Turn a phrase plan into a frame-accurate EDL.

Input is a force-aligned transcript (studio/align.py): every syllable has a CTC
spike time. A phrase keeps one or more word pieces; each cut is placed between
the last kept syllable and the first dropped one, on the quietest point of the
speech envelope (or at the speech onset/release when there is a pause).
Pauses inside a piece longer than MAX_PAUSE are shortened to KEEP_PAUSE.

usage: python build_edl.py <plan.py> <aligned.json> <source48k.wav> <fps> <out.json>
"""
import importlib.util
import json
import re
import sys
import wave

import numpy as np
import opencc

HOP = 0.01          # envelope resolution (s)
THR_DB = -25.0      # speech / pause threshold
PRE_ROLL = 0.05     # kept before a speech onset
POST_ROLL = 0.07    # kept after a speech release
MAX_PAUSE = 0.18    # pauses longer than this inside a piece are shortened
KEEP_PAUSE = 0.08   # ...down to this
SYL_TAIL = 0.09     # a syllable continues at least this long after its spike
SYL_HEAD = 0.04     # ...and starts at least this long before it

DIGITS = "零一二三四五六七八九"


def load_plan(path):
    spec = importlib.util.spec_from_file_location("plan", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def envelope(wav_path):
    wf = wave.open(wav_path)
    sr = wf.getframerate()
    a = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    h = int(sr * HOP)
    n = len(a) // h
    rms = np.sqrt((a[: n * h].reshape(n, h) ** 2).mean(1))
    rms = np.convolve(rms, np.ones(3) / 3, mode="same")   # 30 ms smoothing
    return 20 * np.log10(rms + 1e-9)


def token_stream(tr):
    """[(token, time)] in time order; CJK = one syllable, latin word = one token."""
    toks = []
    for seg in tr["segments"]:
        ws = seg["words"]
        for i, w in enumerate(ws):
            if w.get("chars") and not re.fullmatch(r"[A-Za-z]+", w["w"].strip()):
                toks.extend((c, t) for c, t in w["chars"])
            elif w.get("aligned"):
                toks.append((w["w"].strip().lower(), w["s"]))
            elif w["w"].strip():
                # not aligned (latin): shift the ASR time by the nearest aligned word's drift
                near = [x for x in ws if x.get("aligned")]
                drift = 0.0
                if near:
                    ref = min(near, key=lambda x: abs(x["s_asr"] - w["s"]))
                    drift = ref["s"] - ref["s_asr"]
                toks.append((w["w"].strip().lower(), w["s"] + drift))
    toks.sort(key=lambda x: x[1])
    return toks


def norm_piece(txt):
    txt = re.sub(r"\d+", lambda m: "".join(DIGITS[int(c)] for c in m.group()), txt)
    return re.sub(r"\s+", "", txt.lower())


def find_piece(toks, piece, near):
    """Index range [i, j) of the token run spelling `piece`, closest to time `near`."""
    flat, owner = "", []
    for k, (tok, _) in enumerate(toks):
        flat += tok
        owner += [k] * len(tok)
    best = None
    for m in re.finditer(re.escape(piece), flat):
        i, j = owner[m.start()], owner[m.end() - 1] + 1
        d = abs(toks[i][1] - near)
        if best is None or d < best[0]:
            best = (d, i, j)
    if best is not None and best[0] <= 3.0:
        return best[1], best[2]
    # fuzzy fallback (characters missing from the aligner vocabulary): best
    # matching run inside a window around the anchor time
    import difflib
    win = [k for k, (_, t) in enumerate(toks) if near - 2.0 <= t <= near + 6.0]
    keys = [toks[k][0] for k in win]
    sm = difflib.SequenceMatcher(a=keys, b=list(piece), autojunk=False)
    blocks = [b for b in sm.get_matching_blocks() if b.size]
    if not blocks or sum(b.size for b in blocks) < 0.6 * len(piece):
        raise SystemExit(f"piece not found near {near}: {piece}")
    # keep the densest chain starting near the first piece character
    i, j = win[blocks[0].a], win[blocks[-1].a + blocks[-1].size - 1] + 1
    return i, j


def cut_start(env, toks, i):
    tk = toks[i][1]
    lo = toks[i - 1][1] + SYL_TAIL if i > 0 else tk - 0.6
    lo = max(lo, tk - 0.8)
    hi = tk - SYL_HEAD
    if hi <= lo:
        return (lo + hi) / 2
    a, b = int(lo / HOP), int(hi / HOP) + 1
    seg = env[a:b]
    quiet = np.where(seg <= THR_DB)[0]
    if len(quiet):
        onset = (a + quiet[-1] + 1) * HOP
        return max(lo, onset - PRE_ROLL)
    return (a + int(np.argmin(seg))) * HOP


def cut_end(env, toks, j):
    tl = toks[j - 1][1]
    hi = toks[j][1] - SYL_HEAD - 0.02 if j < len(toks) else tl + 0.8
    hi = min(hi, tl + 0.8)
    lo = tl + SYL_TAIL
    if hi <= lo:
        return (lo + hi) / 2
    a, b = int(lo / HOP), int(hi / HOP) + 1
    seg = env[a:b]
    quiet = np.where(seg <= THR_DB)[0]
    if len(quiet):
        release = (a + quiet[0]) * HOP
        return min(hi, release + POST_ROLL)
    return (a + int(np.argmin(seg))) * HOP


def split_pauses(env, s, e):
    """Split [s,e] around internal pauses longer than MAX_PAUSE."""
    i0, i1 = int(round(s / HOP)), int(round(e / HOP))
    quiet = env[i0:i1] <= THR_DB
    parts, cur, j = [], s, 0
    while j < len(quiet):
        if quiet[j]:
            k = j
            while k < len(quiet) and quiet[k]:
                k += 1
            ps, pe = (i0 + j) * HOP, (i0 + k) * HOP
            if pe - ps > MAX_PAUSE and ps > s + 0.05 and pe < e - 0.05:
                half = KEEP_PAUSE / 2
                parts.append((cur, ps + half))
                cur = pe - half
            j = k
        else:
            j += 1
    parts.append((cur, e))
    return parts


def split_units(text):
    units, i = [], 0
    while i < len(text):
        if text[i].isascii() and text[i].isalnum():
            j = i
            while j < len(text) and text[j].isascii() and text[j].isalnum():
                j += 1
            units.append(text[i:j]); i = j
        else:
            units.append(text[i]); i += 1
    return units


def build(plan_path, tr_path, wav_path, fps, out_path):
    plan = load_plan(plan_path)
    env = envelope(wav_path)
    toks = token_stream(json.load(open(tr_path)))
    fdur = 1.0 / fps

    clips, phrases = [], []
    out_f = 0
    for ph in plan.PHRASES:
        ranges, spikes = [], []
        for item in ph["say"]:
            near, piece = item[0], item[1]
            force = item[2] if len(item) > 2 else {}      # manual cut points (seconds)
            i, j = find_piece(toks, norm_piece(piece), near)
            s = force.get("start", cut_start(env, toks, i))
            e = force.get("end", cut_end(env, toks, j))
            ranges.extend(split_pauses(env, s, e))
            spikes.extend(t for _, t in toks[i:j])
        ph_clips = []
        for s, e in ranges:
            fi, fo = int(round(s * fps)), int(round(e * fps))
            prev = ph_clips[-1] if ph_clips else (clips[-1] if clips else None)
            if prev and prev["src_in_f"] < fi < prev["src_out_f"]:
                fi = prev["src_out_f"]           # contiguous in the source: never replay a frame
            if fo - fi < 2:
                continue
            ph_clips.append(dict(phrase=ph["id"], src_in_f=fi, src_out_f=fo, out_f=out_f,
                                 src_in=fi * fdur, src_out=fo * fdur, out=out_f * fdur,
                                 zoom=ph.get("zoom", "wide")))
            out_f += fo - fi
        clips.extend(ph_clips)

        def to_out(t):
            for c in ph_clips:
                if c["src_in"] - 1e-6 <= t < c["src_out"]:
                    return c["out"] + (t - c["src_in"])
            nxt = [c for c in ph_clips if c["src_in"] > t]
            return nxt[0]["out"] if nxt else ph_clips[-1]["out"]

        # subtitle timing: display units mapped onto spoken syllables in order
        units = split_units(ph["text"])
        speak = [u for u in units if u.strip() and u not in "，、。！？：・"]
        reveal = [max(ph_clips[0]["out"], to_out(t - 0.06)) for t in spikes]
        times, k = [], 0
        for u in units:
            if u.strip() and u not in "，、。！？：・":
                # spread when display/spoken counts differ (e.g. "5000" vs 五千)
                idx = min(len(reveal) - 1, int(round(k * (len(reveal) - 1) / max(1, len(speak) - 1)))) \
                    if len(speak) != len(reveal) else k
                times.append(reveal[idx]); k += 1
            else:
                times.append(times[-1] if times else reveal[0])
        times = list(np.maximum.accumulate(times))
        end = ph_clips[-1]["out"] + (ph_clips[-1]["src_out"] - ph_clips[-1]["src_in"])
        phrases.append(dict(id=ph["id"], text=ph["text"], kw=ph.get("kw", []), fx=ph.get("fx"),
                            zoom=ph.get("zoom", "wide"), units=units,
                            unit_times=[round(t, 3) for t in times],
                            start=ph_clips[0]["out"], end=end))

    json.dump(dict(fps=fps, frames=out_f, duration=out_f / fps, clips=clips, phrases=phrases),
              open(out_path, "w"), ensure_ascii=False, indent=1)
    n = sum(1 for p in phrases for u in p["units"] if u.strip() and u not in "，、。！？：・")
    print(f"{len(clips)} clips, {len(phrases)} phrases, {out_f} frames = {out_f / fps:.2f}s, "
          f"{n / (out_f / fps):.2f} chars/s")


if __name__ == "__main__":
    build(sys.argv[1], sys.argv[2], sys.argv[3], float(eval(sys.argv[4])), sys.argv[5])
