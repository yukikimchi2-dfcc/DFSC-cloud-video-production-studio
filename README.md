# DFSC-cloud-video-production-studio
Cloud-based AI video production system for Dream Factory. Python, FFmpeg, motion graphics, automated editing, GPU rendering, Google Drive integration and team collaboration.

## Interview reel pipeline (`studio/`)

Turns a raw contestant interview into a Dream Factory–style vertical reel (hook → name card → story → insight → CTA → brand outro). The style is measured from the reference reel 「創業之前 先聽這句」.

| Step | Script | What it does |
|---|---|---|
| 1 | `transcribe.py` | Whisper large-v3 transcript with word times (VAD on) |
| 2 | `align.py` | character-level forced alignment (wav2vec2 XLSR Chinese + CTC Viterbi) |
| 3 | `build_edl.py` | phrase plan → frame-accurate EDL; cuts between syllables on the speech envelope; long pauses shortened |
| 4 | `assemble.py` | frame-accurate A-roll and sample-exact speech track |
| 5 | `audio.py`, `music.py` | speech clean-up, original MIDI-composed music rendered with FluidSynth (royalty-free), key-word SFX, ducking, −14 LUFS |
| 6 | `render.py` | face-tracked framing, punch-ins, glitch/shake/zoom-through cut effects, logo, title boxes, serif emphasis, emoji stickers, karaoke-style subtitles (`--no-overlays` for a text-free A-roll) |
| 7 | `finalize.py` | dissolve into the reused brand outro, final encode |
| 8 | `export.py` | SRT, styled ASS, cut list CSV, graphics cue CSV, CMX3600 EDL, FCPXML |

`gfx.py` holds the visual system (colours, fonts, boxes, animations) shared by all projects.

### A project

```
projects/<name>/
  plan.py        what she/he says, in which order (pieces of the transcript) + subtitle text + keywords
  titles.py      on-screen titles / stickers, anchored to spoken words
  assets/        logo files
  build.sh       RAW=... REF=... [WORK=...] [OUT=...] [FROM=step] ./build.sh
  deliverables/  final video, subtitles, logo, stems, cut lists, report
```

Requirements: `ffmpeg` (with libass/librubberband), `fluidsynth` + `fluid-soundfont-gm`, Python 3 with `faster-whisper`, `torch`, `transformers`, `opencv-python-headless<5`, `opencc-python-reimplemented`, `pillow`, `numpy`, `scipy`, `mido`, `pyloudnorm`, and the Noto CJK + Noto Color Emoji fonts.

### Projects
- `projects/catherine_pang/` — Catherine Pang · 洪記糖水 · 第九屆參賽者 (see `deliverables/Editing_Report.md`)
