"""Editable/interchange exports for a finished cut.

Writes into <out_dir>:
  Subtitle.srt            subtitles on the final timeline (one line per card, as on screen)
  Subtitle.ass            same, with the reference style (font, size, colours, outline, keyword green)
  cut_list.csv            every A-roll clip: source timecode in/out -> record timecode in/out
  graphics_cues.csv       every title card / sticker with its time range (to rebuild in any editor)
  Edit_Decision_List.edl  CMX3600 EDL of the A-roll cuts (relinks to the raw interview file)
  Timeline.fcpxml         FCPXML 1.9: A-roll cuts + outro + watermark + music/SFX stems

usage: python export.py <edl.json> <titles.py> <out_dir> --src-tc HH:MM:SS:FF [--outro-in 54.02]
                        [--outro-dur 9.13] [--talk-mix mix_talk.wav]
"""
import csv
import json
import os
import sys
from fractions import Fraction
from xml.sax.saxutils import escape

sys.path.insert(0, os.path.dirname(__file__))
from render import Anchors, Subtitles, Title, load_mod  # noqa: E402

FPS_NUM, FPS_DEN = 24000, 1001
TC_FPS = 24                                    # 23.976 is counted as 24 fps NDF timecode


def tc(frames):
    f = frames % TC_FPS
    s = frames // TC_FPS
    return f"{s // 3600:02d}:{s // 60 % 60:02d}:{s % 60:02d}:{f:02d}"


def tc_to_frames(s):
    h, m, sec, f = (int(x) for x in s.split(":"))
    return ((h * 60 + m) * 60 + sec) * TC_FPS + f


def srt_time(t):
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def ass_time(t):
    cs = int(round(t * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def rt(frames):
    """rational FCPXML time for a frame count"""
    v = Fraction(frames * FPS_DEN, FPS_NUM)
    return f"{v.numerator}/{v.denominator}s" if v.denominator != 1 else f"{v.numerator}s"


def main():
    edl_path, titles_path, out = sys.argv[1:4]
    arg = lambda k, d=None: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d  # noqa: E731
    src_tc = tc_to_frames(arg("--src-tc", "00:00:00:00"))
    outro_in = float(arg("--outro-in", "54.02"))
    outro_dur = float(arg("--outro-dur", "9.13"))
    edl = json.load(open(edl_path))
    fps = edl["fps"]
    os.makedirs(out, exist_ok=True)
    anchors = Anchors(edl)
    subs = Subtitles(edl)

    # ---- SRT / ASS ----
    items = [it for it in subs.items]
    with open(f"{out}/Subtitle.srt", "w", encoding="utf-8") as f:
        for i, it in enumerate(items, 1):
            text = "".join(it["line"].units)
            f.write(f"{i}\n{srt_time(it['start'])} --> {srt_time(it['end'])}\n{text}\n\n")
    head = """[Script Info]
Title: Catherine Pang - Dream Factory interview
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: DF_Sub,Noto Sans CJK TC,64,&H00FCFAF9,&H00FCFAF9,&H00140E0C,&H8C000000,-1,0,0,0,100,100,0,0,1,3,2,5,40,40,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    with open(f"{out}/Subtitle.ass", "w", encoding="utf-8") as f:
        f.write(head)
        for it in items:
            units, mask = it["line"].units, None
            # keyword runs in green (reference #68D468) with underline
            ph = next(p for p in edl["phrases"] if p["id"] == it["phrase"])
            joined = "".join(units)
            green = [False] * len(units)
            for kw in ph["kw"]:
                pos = joined.find(kw)
                acc = 0
                for k, u in enumerate(units):
                    if pos >= 0 and pos <= acc < pos + len(kw):
                        green[k] = True
                    acc += len(u)
            txt, on = "", False
            for k, u in enumerate(units):
                if green[k] and not on:
                    txt += r"{\c&H68D468&\u1}"; on = True
                if not green[k] and on:
                    txt += r"{\c&HFCFAF9&\u0}"; on = False
                txt += u
            f.write(f"Dialogue: 0,{ass_time(it['start'])},{ass_time(it['end'])},DF_Sub,,0,0,0,,"
                    f"{{\\pos(540,1300)}}{txt}\n")

    # ---- cut list + CMX3600 EDL ----
    clips = edl["clips"]
    with open(f"{out}/cut_list.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["#", "phrase", "subtitle", "source TC in", "source TC out", "source sec in", "source sec out",
                    "record TC in", "record TC out", "duration (s)", "framing"])
        texts = {p["id"]: p["text"] for p in edl["phrases"]}
        for i, c in enumerate(clips, 1):
            n = c["src_out_f"] - c["src_in_f"]
            w.writerow([i, c["phrase"], texts[c["phrase"]], tc(src_tc + c["src_in_f"]), tc(src_tc + c["src_out_f"]),
                        f"{c['src_in']:.3f}", f"{c['src_out']:.3f}", tc(c["out_f"]), tc(c["out_f"] + n),
                        f"{n / fps:.3f}", c["zoom"]])
        total = edl["frames"]
        w.writerow(["outro", "brand outro (reused from reference video 1)", "", "", "", f"{outro_in:.3f}",
                    f"{outro_in + outro_dur:.3f}", tc(total), tc(total + round(outro_dur * fps)),
                    f"{outro_dur:.3f}", "0.25 s dissolve"])
    rec0 = 3600 * TC_FPS                                   # record starts at 01:00:00:00
    with open(f"{out}/Edit_Decision_List.edl", "w") as f:
        f.write("TITLE: CATHERINE_PANG_DFSC\nFCM: NON-DROP FRAME\n\n")
        for i, c in enumerate(clips, 1):
            n = c["src_out_f"] - c["src_in_f"]
            f.write(f"{i:03d}  RAW      AA/V  C        {tc(src_tc + c['src_in_f'])} {tc(src_tc + c['src_out_f'])} "
                    f"{tc(rec0 + c['out_f'])} {tc(rec0 + c['out_f'] + n)}\n")
            f.write(f"* FROM CLIP NAME: CatherinePang_raw_interview.mp4\n* COMMENT: {c['phrase']}\n\n")

    # ---- graphics cues ----
    titles = [Title(s, anchors) for s in load_mod(titles_path).TITLES]
    with open(f"{out}/graphics_cues.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["type", "start (s)", "end (s)", "start TC", "end TC", "text", "style", "size", "centre y (px)",
                    "emoji / sticker"])
        for t in titles:
            s = t.s
            text = s.get("text") or s.get("name") or f"{s.get('left', '')} {s.get('right', '')}".strip()
            if s["type"] == "rows":
                text = " / ".join(r[1] for r in s["rows"])
            if s["type"] == "name":
                text = f"{s['name']} | {s['tag']}"
            emo = " ".join(x for x in [s.get("emoji"), s.get("emoji2"), s.get("icon")] if x)
            if s["type"] == "name":
                emo = f"{s['left']} {s['right']}"
            w.writerow([s["type"], f"{t.t0:.2f}", f"{t.t1:.2f}", tc(round(t.t0 * fps)), tc(round(t.t1 * fps)),
                        text, s.get("style", ""), s.get("size", ""), s.get("cy", ""), emo])

    # ---- FCPXML 1.9 ----
    total = edl["frames"]
    outro_f = round(outro_dur * fps)
    src_start = rt(src_tc)
    xml = [f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE fcpxml>
<fcpxml version="1.9">
  <resources>
    <format id="r1" name="FFVideoFormat1080x1920p2398" frameDuration="1001/24000s" width="1080" height="1920" colorSpace="1-1-1 (Rec. 709)"/>
    <asset id="r2" name="CatherinePang_raw_interview" start="{src_start}" duration="{rt(6215)}" hasVideo="1" hasAudio="1" format="r1" audioSources="1" audioChannels="2" audioRate="48000">
      <media-rep kind="original-media" src="file:///RELINK/CatherinePang_raw_interview.mp4"/>
    </asset>
    <asset id="r3" name="DFSC_brand_outro" start="0s" duration="{rt(outro_f)}" hasVideo="1" hasAudio="1" format="r1" audioSources="1" audioChannels="2" audioRate="48000">
      <media-rep kind="original-media" src="file:///RELINK/DFSC_brand_outro.mp4"/>
    </asset>
    <asset id="r4" name="BGM_original" start="0s" duration="{rt(total)}" hasAudio="1" audioSources="1" audioChannels="2" audioRate="48000">
      <media-rep kind="original-media" src="file:///RELINK/stems/bgm.wav"/>
    </asset>
    <asset id="r5" name="SFX" start="0s" duration="{rt(total)}" hasAudio="1" audioSources="1" audioChannels="2" audioRate="48000">
      <media-rep kind="original-media" src="file:///RELINK/stems/sfx.wav"/>
    </asset>
    <asset id="r6" name="dreamfactory_watermark" start="0s" duration="0s" hasVideo="1" format="r1">
      <media-rep kind="original-media" src="file:///RELINK/Logo_Transparent_White.png"/>
    </asset>
  </resources>
  <library>
    <event name="DFSC Catherine Pang">
      <project name="CatherinePang_洪記糖水_editable">
        <sequence format="r1" duration="{rt(total + outro_f)}" tcStart="0s" tcFormat="NDF" audioLayout="stereo" audioRate="48k">
          <spine>''']
    for i, c in enumerate(clips):
        n = c["src_out_f"] - c["src_in_f"]
        name = escape(f"{c['phrase']} {next(p['text'] for p in edl['phrases'] if p['id'] == c['phrase'])}")
        inner = ""
        if i == 0:
            st = src_tc + c["src_in_f"]
            inner = (f'\n              <asset-clip ref="r4" lane="-1" offset="{rt(st)}" start="0s" duration="{rt(total)}" name="BGM (original, royalty-free)"/>'
                     f'\n              <asset-clip ref="r5" lane="-2" offset="{rt(st)}" start="0s" duration="{rt(total)}" name="SFX"/>'
                     f'\n              <video ref="r6" lane="1" offset="{rt(st)}" start="0s" duration="{rt(total)}" name="watermark (x35 y62 w172)"/>\n            ')
        xml.append(f'            <asset-clip ref="r2" offset="{rt(c["out_f"])}" start="{rt(src_tc + c["src_in_f"])}" '
                   f'duration="{rt(n)}" name="{name}" tcFormat="NDF">{inner}</asset-clip>')
    xml.append(f'            <asset-clip ref="r3" offset="{rt(total)}" start="0s" duration="{rt(outro_f)}" name="DFSC brand outro"/>')
    xml.append('''          </spine>
        </sequence>
      </project>
    </event>
  </library>
</fcpxml>''')
    open(f"{out}/Timeline.fcpxml", "w", encoding="utf-8").write("\n".join(xml))
    print("exported:", sorted(os.listdir(out)))


if __name__ == "__main__":
    main()
