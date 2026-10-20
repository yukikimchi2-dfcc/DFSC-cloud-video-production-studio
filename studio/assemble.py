"""Cut the raw interview into the A-roll described by an EDL.

Video: every clip is decoded frame-accurately and re-encoded near-losslessly,
then joined with the concat demuxer. Audio: every clip is taken sample-exact
(frames * samples_per_frame) with short edge fades so jump cuts do not click.

usage: python assemble.py <edl.json> <raw.mp4> <workdir>
  -> <workdir>/aroll.mp4 (video only) and <workdir>/speech.wav (48 kHz mono)
"""
import json
import os
import subprocess
import sys
import wave

import numpy as np

SR = 48000
EDGE_FADE = 0.006


def run(cmd):
    subprocess.run(cmd, check=True)


def main(edl_path, raw, work):
    edl = json.load(open(edl_path))
    fps = edl["fps"]
    spf = SR / fps                                     # samples per frame (2002 @ 23.976)
    os.makedirs(f"{work}/clips", exist_ok=True)

    # full-length mono 48k source audio for sample-exact slicing
    src_wav = f"{work}/src48.wav"
    if not os.path.exists(src_wav):
        run(["ffmpeg", "-v", "error", "-y", "-i", raw, "-map", "0:a:0", "-ac", "1", "-ar", str(SR), src_wav])
    wf = wave.open(src_wav)
    src = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32) / 32768

    pieces, lst = [], []
    nf = int(EDGE_FADE * SR)
    ramp = np.linspace(0, 1, nf, dtype=np.float32)
    for i, c in enumerate(edl["clips"]):
        n = c["src_out_f"] - c["src_in_f"]
        out = f"{work}/clips/c{i:03d}.mp4"
        if not os.path.exists(out):
            run(["ffmpeg", "-v", "error", "-y", "-ss", f"{c['src_in']:.6f}", "-i", raw, "-map", "0:v:0",
                 "-frames:v", str(n), "-vf", "format=yuv420p", "-c:v", "libx264", "-preset", "fast",
                 "-crf", "10", "-r", "24000/1001", "-an", out])
        lst.append(f"file '{os.path.abspath(out)}'")
        s0 = int(round(c["src_in_f"] * spf))
        seg = src[s0:s0 + int(round(n * spf))].copy()
        seg[:nf] *= ramp
        seg[-nf:] *= ramp[::-1]
        pieces.append(seg)
    open(f"{work}/clips.txt", "w").write("\n".join(lst) + "\n")
    run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", f"{work}/clips.txt",
         "-c", "copy", f"{work}/aroll.mp4"])
    speech = np.concatenate(pieces)
    with wave.open(f"{work}/speech.wav", "w") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((np.clip(speech, -1, 1) * 32767).astype(np.int16).tobytes())
    print("frames", edl["frames"], "audio s", len(speech) / SR, "video s", edl["frames"] / fps)


if __name__ == "__main__":
    main(*sys.argv[1:4])
