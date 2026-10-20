#!/usr/bin/env bash
# Rebuild the Catherine Pang cut end-to-end.
#   RAW  = raw interview (video 2)      REF = Dream Factory reference (video 1)
#   WORK = scratch folder               OUT = deliverables folder
# Edit plan.py (what is said / subtitle text) or titles.py (on-screen graphics),
# then run this script again.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
STUDIO="$HERE/../../studio"
RAW="${RAW:?path to raw interview}"; REF="${REF:?path to reference video}"
WORK="${WORK:-/tmp/catherine_work}"; OUT="${OUT:-$HERE/deliverables}"
LOGO_WHITE="$HERE/assets/Logo_Transparent_White.png"
FROM="${FROM:-1}"                     # resume from a step (1-5)
mkdir -p "$WORK/build" "$OUT/stems"

# 1. transcript + forced alignment (cached)
if [ "$FROM" -le 1 ] && [ ! -f "$WORK/raw_aligned.json" ]; then
  ffmpeg -v error -y -i "$RAW" -map 0:a:0 -ac 1 -ar 16000 "$WORK/raw16.wav"
  python3 "$STUDIO/transcribe.py" large-v3 "$WORK/raw16.wav" "$WORK/raw_tr.json"
  python3 "$STUDIO/align.py" "$WORK/raw_tr.json" "$WORK/raw16.wav" "$WORK/raw_aligned.json"
fi
[ -f "$WORK/raw48.wav" ] || ffmpeg -v error -y -i "$RAW" -map 0:a:0 -ac 1 -ar 48000 "$WORK/raw48.wav"

# 2. edit decision list + A-roll
if [ "$FROM" -le 2 ]; then
  python3 "$STUDIO/build_edl.py" "$HERE/plan.py" "$WORK/raw_aligned.json" "$WORK/raw48.wav" 24000/1001 "$WORK/edl.json"
  rm -rf "$WORK/build/clips"
  python3 "$STUDIO/assemble.py" "$WORK/edl.json" "$RAW" "$WORK/build"
fi

# 3. sound: speech clean-up, original music, SFX, -14 LUFS mix
[ "$FROM" -le 3 ] && python3 "$STUDIO/audio.py" "$WORK/edl.json" "$HERE/titles.py" "$WORK/build/speech.wav" "$WORK/build"

# 4. pictures: styled cut + text-free A-roll
if [ "$FROM" -le 4 ]; then
python3 "$STUDIO/render.py" "$WORK/edl.json" "$HERE/titles.py" "$WORK/build/aroll.mp4" "$LOGO_WHITE" "$WORK/build/video_talk.mp4"
python3 "$STUDIO/render.py" "$WORK/edl.json" "$HERE/titles.py" "$WORK/build/aroll.mp4" "$LOGO_WHITE" "$WORK/build/video_clean.mp4" --no-overlays
fi

# 5. outro + final files
python3 "$STUDIO/finalize.py" "$WORK/build/video_talk.mp4" "$WORK/build/mix_talk.wav" "$REF" "$OUT/Final_Edit.mp4" \
  --outro-out "$OUT/DFSC_品牌片尾_第十一屆.mp4"
ffmpeg -v error -y -i "$WORK/build/video_clean.mp4" -i "$WORK/build/mix_talk.wav" -map 0:v -map 1:a -c:v copy \
  -c:a aac -b:a 256k -movflags +faststart "$OUT/CatherinePang_A-roll_無字卡.mp4"
for s in speech_proc bgm sfx mix_talk; do cp "$WORK/build/$s.wav" "$OUT/stems/$s.wav"; done
python3 "$STUDIO/export.py" "$WORK/edl.json" "$HERE/titles.py" "$OUT" --src-tc 22:25:36:12
cp "$WORK/edl.json" "$OUT/edl.json"
echo "done -> $OUT"
