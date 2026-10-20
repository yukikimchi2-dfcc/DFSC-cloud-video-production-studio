# Editing Report — Catherine Pang · 洪記糖水 · 第九屆參賽者

| | |
|---|---|
| Reference style | Video 1 — Dream Factory「創業之前 先聽這句」(AK 關德輝), 63.1 s |
| Raw footage | Video 2 — Catherine Pang interview, 4:19, DJI, HEVC 10-bit 1080×1920 23.976 fps |
| Output | `Final_Edit.mp4` — 1080×1920, 23.976 fps, H.264 High (CRF 18, ≤ 9 Mbps), AAC 256 kbps 48 kHz, −14.0 LUFS / −1.5 dBTP |
| Length | 82.2 s = 73.1 s interview + 9.1 s brand outro (reference: 53.9 s + 9.1 s) |

---

## 1. Reference analysis (video 1) — measured values

| Item | Measured on video 1 | Applied to Catherine's cut |
|---|---|---|
| Format | 1080×1920 (9:16), 23.976 fps, H.264 ≈ 9.1 Mbps, AAC 48 kHz | identical (7.7 Mbps average) |
| Pace | 280 characters in 53.5 s = **5.24 characters/s**, longest pause 0.36 s, mean pause 0.13 s, no speed change | **5.20 characters/s**, pauses > 0.18 s shortened to 0.08 s, no speed change (natural voice, no pitch change) |
| Hook | Header box「創業之前　先聽這句」+ 👂 from frame 0, the speaker's strongest line first, name card at ~8 s | same header, same layout, her strongest line first, name card at 5.8 s |
| Subtitles | Bold sans (思源黑體/Noto Sans CJK–style) ≈ 64 px, white `#F9FAFC`, dark outline + soft drop shadow, centred at y ≈ 1300, one line ≤ ~14 characters. Layout is fixed for the whole phrase and characters appear as they are spoken (2-frame fade). Keywords green `#68D468` with a green underline bar `#43AC47` | Noto Sans CJK TC Bold 64 px, identical colours/outline/shadow/position. Character reveal is driven by forced alignment, so every character appears on its syllable. |
| Title boxes | Navy box: gradient `#122648`→`#0F1A31`, 2 px border `#75777F`, faint stripes, white text + green `#6AD969` keyword, ≈ 108 px. Green box: horizontal gradient `#54C854`→`#3A893A`, white text. White tag `#EFF1EC` with black/grey text. Two-tier variant (small label + big box). Stacked rows variant (Due Diligence / Compliance) | identical construction, sizes 108 / 64 / 50 px (Noto Sans CJK TC Black) |
| Title motion | Box grows horizontally from a thin bar (~5 frames), characters fade in one by one, a diagonal light sweep crosses the box, a star glint flashes at the top-right corner, emoji sticker pops in, reverse on exit | identical |
| Emphasis words | Big serif (粗明體 style) white or green, dark outline, characters zoom in from blur, gold sparkles, RGB-glitch on entry (「不簡單」「極高」「等你來挑戰」) | Noto Serif CJK TC Black 168 px: 「不辛苦」「掉到最谷底」「負債累累」「苦中的甜」「才是最甜」「一起加油」 |
| Framing | Medium close-up, face centre ≈ 43 % of height, two framings alternating (punch-ins), titles above the head | face-tracked (per phrase), face centre at 44 %, framings 1.10× / 1.27×, plus a 2.5 % slow push-in per phrase |
| Cut effects | jump cuts; RGB split/glitch on emphasis; camera shake; ghost/zoom-blur transition between sections; dissolve into outro | glitch (hook, 「才是最甜」, every serif entry), shake (「掉到最谷底」), ghost/zoom-blur (into the story and into the insight section), 0.25 s dissolve into outro |
| Logo | 「dream factory 圓夢工場」, white + green version, top-left x 35 y 62, width 172 px, 100 % opacity, on screen from frame 0 until the outro | identical position/size/timing (see §6) |
| Music | quiet sustained pad under the first ~70 %, fuller groove from ~38 s, outro has its own music + whoosh | original music, same arc: pad + e-piano first, bass/drums from the insight section (45 s), hands over to the outro's own music |
| SFX | accents on title/keyword moments | 46 cues: whoosh + glint on big boxes, swish on small boxes/rows, pop on stickers/✅, impact + glitch on serif words, thump on shake, whoosh on blur transitions |
| Outro | 54.0 → 63.1 s: starfield 「第十一屆，三個賽道 創意 / 成長 / 轉型」→ green clouds →「圓夢工場・創業大賽 / Dream Factory Startup Contest / 啟航北極星 / 預熱開放報名 dreamfactory.my」 | **original outro reused unchanged** (picture + sound), same dissolve |
| Loudness | talk −13.9 LUFS, outro −13.4 LUFS | talk −14.0 LUFS, outro kept at its original level |

## 2. Hook selection

Three candidates from Catherine's own words (source timecodes in the raw file):

| # | Line (verbatim) | Source | Strengths | Weaknesses |
|---|---|---|---|---|
| **A ✅** | 「很多人都覺得創業很辛苦，其實創業不辛苦的，只是你要來到對的地方，對的平台。」 | 3:10.4 – 3:16.3 | Contrarian twist inside the first 2 s (everyone agrees → she disagrees), opens a "why?" curiosity gap, speaks to the target audience (would-be founders), pays off at the end (the contest = the right platform) | needs the story afterwards to earn it — which the cut provides |
| B | 「我剛剛好40歲的時候，一個疫情，就是從最高峰的時候，掉到最谷底。」 | 1:16.4 – 1:22.9 | strong emotion and drama | the punch arrives only after ~5 s; viewers don't yet know who she is |
| C | 「熬過的苦……你才會覺得苦中的甜，才是最甜。」 | 3:37 – 3:42 | poetic, ties perfectly to her 糖水 business | it is the conclusion — used as the hook it gives the ending away and has no tension in 1–3 s |

**Chosen: A.** It mirrors the reference's hook structure exactly (a piece of founder wisdom under the「創業之前 先聽這句」header), is understandable without context, and B and C stay in the body where they work best: B is the story's turning point, and C is the emotional ending before the CTA.

## 3. Story structure (73.1 s)

| Time | Section | Content (her words only) |
|---|---|---|
| 0:00 | Hook | 很多人都覺得創業很辛苦 / 其實創業不辛苦的 / 只是你要來到對的地方，對的平台 |
| 0:05.8 | Intro + name card | 我是甜大姐 Catherine Pang / 從事糖水行業 / 擁有自己的中央廚房 |
| 0:11.3 | Why start a business | 創業才是我要的東西 / 不是那種朝九晚五的乖乖派 |
| 0:17.6 | Story | 第三次創業 → 30歲第一次創業，吉隆坡最大的批發市場，批發辣椒，啟動資金不到5000塊 → 40歲疫情，從最高峰掉到最谷底 → 41歲為了還債重新創業，第二次啟動資金是零，負債累累 → 起起跌跌、踩了很多坑 → 45歲才正式創業 |
| 0:45.0 | Insight | 天下沒有白走的路 / 為什麼參加第九屆圓夢創業大賽：資源、平台、正能量互相扶持的夥伴 |
| 0:58.8 | Message | 最重要是你肯熬過去 / 苦中的甜才是最甜 |
| 1:05.8 | CTA | 希望在來臨的第十一屆圓夢工場創業大賽裡面見到你，我們一起互相加油 (ends on her wink) |
| 1:13.1 | Outro | reference brand outro |

The answer order was rearranged (hook moved to the top; the start-up capital answers were moved into the story where each venture is mentioned). No sentence was altered in meaning. Every cut was re-checked by transcribing the finished audio (§7).

## 4. What was removed

**Interviewer and crew (never used: picture, voice or text)**
- 0:00 – 0:26 crew set-up chatter (「這是什麼題目」「安川你要給我什麼」…)
- 0:27 – 0:30 「請問你現在是在創業還是在打工」
- 0:42 – 0:44 「那你當初為什麼選擇創業，不是打工」
- 1:37 – 1:40 「那你的第一筆啟動資金是多少」
- ~2:17 – 2:23 off-mic question (not transcribable)
- 2:46 – 2:54 「好，謝謝你……我現在就濃縮你這樣多年來的經驗跟坑的話」
- 3:43 – 4:09 crew instructions about the closing line (「最後是第十一屆…加一句呼籲…」)
- 4:17.4 – end: off-camera voice after her final 「加油」

Identification: the interviewer is off-camera and ~12 dB quieter on Catherine's lavalier (−22…−28 dB vs −10…−15 dB), confirmed by content.

**Repeated / off-thread content (kept out for pace; can be restored in `plan.py`)**
- 「你可以叫我田大姐」 (second self-introduction), 「我目前是在創業」, 「哈囉你好」
- 「其實這個夢想，現在這個年紀來講」 (unfinished sentence with a 4-second hesitation)
- 1:57 – 2:17 second telling of the wholesale-market story (imported chillies from China / Vietnam / Thailand / Indonesia)
- 2:23 – 2:46 answer to "if someone gave you RM100k" (expand the central kitchen, go for halal certification). This is a valid point, but a separate topic.
- third start-up capital 「不到一萬塊」, the recap 「30歲、40歲、41歲、45歲的創業」, the repeated 「創業是其實不辛苦的」 (used as the hook instead)

**Fillers, stutters, false starts (inside sentences)**
- 「然後」「就是」「我覺得」(repeated), 「那種」(repeated), 「也有…擁有」→「擁有」, 「因為為了」→「為了」, 「正式來講」, 「45歲開始的時候才開始」→「45歲的時候才開始」, 「我就…」, the false start 「創…圓夢創業大賽」, the self-correction 「有一班……一群」→「有一群」
- all pauses longer than 0.18 s → 0.08 s (natural breath kept); every cut sits on the quietest point between two syllables, with 6 ms audio fades so no clicks

## 5. Technical pipeline (all executed; source in `studio/`)

1. `transcribe.py` — Whisper large-v3 (VAD on; without VAD it hallucinates on the crew chatter)
2. `align.py` — character-level forced alignment (wav2vec2-XLSR Chinese, CTC Viterbi). Whisper's word times were 0.2 – 0.3 s off, which left stray syllables at cuts; alignment fixed that.
3. `build_edl.py` — phrases from `projects/catherine_pang/plan.py` → frame-accurate EDL (56 clips, 45 phrases), cut points on the speech envelope, pause shortening, subtitle timing per character
4. `assemble.py` — frame-accurate A-roll from the 10-bit HEVC + sample-exact audio
5. `audio.py` — speech clean-up (HPF 80 Hz, light FFT denoise, gentle de-ess, 2.5:1 compression), original music, SFX, ducking (−5 dB under speech), loudness −14 LUFS
6. `render.py` — face tracking, framing, cut effects, logo, titles, stickers, sparkles, subtitles
7. `finalize.py` — 0.25 s dissolve into the reused outro, final encode
8. `export.py` — SRT / ASS / cut list / graphics cues / CMX3600 EDL / FCPXML

Rebuild everything with `projects/catherine_pang/build.sh` (edit `plan.py` to change wording or cuts, `titles.py` to change titles/stickers, swap `assets/Logo_Transparent_White.png` to change the logo).

## 6. Logo

- Source: video 1 outro, 61.4 – 63.0 s (logo on a flat `#ECECEC` background — the cleanest view in the video). 39 frames were registered (sub-pixel phase correlation, because the logo floats slightly) and median-combined at 4× resolution, then keyed by solving alpha against the known background for the two logo inks.
- Colours measured: green `#3EAC4E`, dark grey `#414141`.
- `Logo_Transparent.png` — original colours (as in the outro), 789×479 px, transparent.
- `Logo_Transparent_White.png` — the on-video variant used in video 1 (「dream」 and 「圓夢工場」 in white, 「factory」 and the cloud green).
- Shape, font, proportions and colours were **extracted, not redrawn**. Limitation: the logo is only ~190 px wide in the video, so the 4× PNG is reconstructed from that resolution — the fine strokes of 「圓夢工場」 are slightly soft. For print or large use, replace it with the official vector file.

## 7. Quality check (done on the exported file)

| Check | Result |
|---|---|
| Interviewer visible / audible? | No. The interviewer is never on camera; every kept range is Catherine's mic level, and a final ASR pass finds no question text. |
| Fillers / stutters left? | A final Whisper pass of `Final_Edit.mp4` reads exactly the planned script (only homophone ASR misspellings such as 田/甜, 古/谷). |
| Hook from video 2? | Yes, verbatim, 3:10.4 – 3:16.3 of the raw file. |
| Subtitle sync | Characters appear at their aligned syllable (−60 ms lead); one line per card, same as video 1. |
| Pace vs video 1 | 5.20 vs 5.24 characters/s; average clip 1.30 s; no speed change. |
| Logo vs reference | same artwork, position, size and timing. |
| Ending | the reference outro is reused unchanged after a 0.25 s dissolve, with its own music. |
| Loudness | −14.0 LUFS integrated, −1.5 dBTP, LRA 1.6 LU. |

## 8. Not 100 % reproducible — please review

1. **Her nickname**: ASR heard 「田大姐」. I used **「甜大姐」** (same sound, fits a 糖水 brand). Her Chinese name is unknown, so the name card shows **Catherine Pang** with 「洪記糖水 ・ 第九屆參賽者」. Change both in `plan.py` / `titles.py` if needed.
2. **Fonts**: the reference's exact commercial fonts are not identifiable from video. Noto Sans CJK TC (= 思源黑體) and Noto Serif CJK TC (= 思源宋體) are visually the closest open-licence matches.
3. **Emoji stickers**: the reference uses Apple-style emoji, which are not licensable here. Noto Color Emoji is used with the same white sticker outline and animation.
4. **Music & SFX**: the reference's library tracks are unknown. Both are **original, synthesised in this pipeline**, so they contain no third-party recordings, are safe for commercial use, and cannot trigger Facebook/Instagram rights claims.
5. **Background**: Catherine was filmed in front of a busy event banner (「下一站 走向IPO / THE SANDBOX」) that sits behind the logo, whereas the reference had a plain wall. The logo has a faint soft shadow to stay legible. This is the only visual addition.
6. **Subtitle wording**: lightly normalised where she slipped:「每一走的一步」→「每走的一步都算數」, ASR 「早九晚五」→「朝九晚五」, 「中央出發」→「中央廚房」, 「最古頂」→「最谷底」, 「也大了很多的坑」→「也踩了很多的坑」, 「圓夢工廠」→「圓夢工場」. Simplified ASR output was converted to Traditional Chinese to match video 1.
7. **Title wording** summarises her sentences, as in video 1 (e.g. 「一場疫情」「啟動資金：零」). The header 「創業之前 先聽這句」 is reused from video 1 as the series format.

## 9. Files

| File | What |
|---|---|
| `Final_Edit.mp4` | final video |
| `Logo_Transparent.png`, `Logo_Transparent_White.png` | extracted logo, transparent |
| `Subtitle.srt` | subtitles, final timeline (import into CapCut/剪映, Premiere, Resolve, ChatCut) |
| `Subtitle.ass` | same, with the reference style (font, size, colours, keyword green/underline) |
| `CatherinePang_A-roll_無字卡.mp4` | the cut with framing/effects and full sound but **no text, titles or logo** — the base for re-titling |
| `DFSC_品牌片尾_第十一屆.mp4` | the brand outro (from video 1) |
| `stems/` | `speech_proc.wav`, `bgm.wav`, `sfx.wav`, `mix_talk.wav` |
| `cut_list.csv` | every cut: source TC in/out → record TC in/out, subtitle text |
| `graphics_cues.csv` | every title/sticker with start/end time, text, style, size, position |
| `Edit_Decision_List.edl` | CMX3600 EDL (relinks to the raw file, source TC 22:25:36:12) |
| `Timeline.fcpxml` | FCPXML 1.9 for Final Cut / DaVinci Resolve (A-roll cuts, outro, watermark, music, SFX). Relink `file:///RELINK/...` to your local files |
| `edl.json` | machine-readable edit (phrases, clips, subtitle timing) |
| ChatCut project | 「Catherine Pang · 洪記糖水 · 第九屆參賽者」 with the same layout as the Nelson Chin project (editable A-roll + captions + outro + watermark timeline, and the finished cut as reference) |
