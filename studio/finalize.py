"""Join the rendered talk part with the reused brand outro (reference video 1).

The outro is taken from the reference from OUTRO_IN to its end. The reference
dissolves from the speaker into the outro over ~0.25 s; the same dissolve is
rebuilt here (first outro frame held under the dissolve, audio cross-faded).

usage: python finalize.py <talk_video.mp4> <talk_audio.wav> <reference.mp4> <out.mp4> [--outro-out outro.mp4]
"""
import subprocess
import sys

OUTRO_IN = 54.02    # first clean outro frame in the reference (dissolve starts ~53.85)
XFADE = 0.25


def dur(path):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                                 "default=nw=1:nk=1", path], capture_output=True, text=True).stdout)


def main():
    talk_v, talk_a, ref, out = sys.argv[1:5]
    frames = int(subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                                 "stream=nb_read_frames", "-of", "default=nw=1:nk=1", talk_v],
                                capture_output=True, text=True).stdout)
    T = frames * 1001 / 24000
    enc = ["-c:v", "libx264", "-preset", "slow", "-crf", "18", "-maxrate", "9M", "-bufsize", "18M",
           "-pix_fmt", "yuv420p", "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
           "-r", "24000/1001", "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-movflags", "+faststart"]
    fc = (f"[1:v]trim=start={OUTRO_IN},setpts=PTS-STARTPTS,fps=24000/1001,format=yuv420p,"
          f"tpad=start_mode=clone:start_duration={XFADE},settb=AVTB[o];"
          f"[0:v]fps=24000/1001,format=yuv420p,settb=AVTB[m];"
          f"[m][o]xfade=transition=fade:duration={XFADE}:offset={T - XFADE:.5f},format=yuv420p[v];"
          f"[1:a]atrim=start={OUTRO_IN - XFADE},asetpts=PTS-STARTPTS,aresample=48000[oa];"
          f"[2:a]aresample=48000,aformat=channel_layouts=stereo[ta];"
          f"[ta][oa]acrossfade=d={XFADE}:c1=tri:c2=tri[a]")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", talk_v, "-i", ref, "-i", talk_a, "-filter_complex", fc,
                    "-map", "[v]", "-map", "[a]", *enc, out], check=True)
    if "--outro-out" in sys.argv:            # the outro on its own, as an editable asset
        o = sys.argv[sys.argv.index("--outro-out") + 1]
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(OUTRO_IN), "-i", ref, *enc, o], check=True)
    print(f"talk {T:.3f}s + outro -> {dur(out):.3f}s")


if __name__ == "__main__":
    main()
