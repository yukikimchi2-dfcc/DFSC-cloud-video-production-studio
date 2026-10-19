# 品質檢查報告 QC Report — DFCC_YYLim_QJoyBalloon.mp4

- 結果 Result: **未通過 FAILED**
- 檔案 File: `workspace/references/drive/1x4YaQ1NOiW04Wnb_kM-N8N-1uT1sykG8/DFCC_YYLim_QJoyBalloon.mp4`
- 時間 Checked: 2026-10-19 09:30 UTC
- 規格 Specs: 1080x1920 · 60.017 fps · h264/aac · 57.94 s · 161.21 MB

| 狀態 | 檢查項目 Check | 數值 Value | 標準 Expected | 說明 Notes |
|---|---|---|---|---|
| ✅ PASS | 影像編碼 video_codec | h264 | h264 |  |
| ✅ PASS | 像素格式 pixel_format | yuv420p | yuv420p | yuv420p is required for social platforms |
| ✅ PASS | 黑幀檢測 black_frames | [] | none | no unexpected black frames |
| ✅ PASS | 卡幀檢測 frozen_frames | [] | < 0.5s | no frozen segments |
| ⚠️ WARN | 重複幀檢測 duplicate_frames | {"duplicates": 1925, "longest_run": 151, "frames": 3472} | run < 3 | 1925 duplicate frame(s), longest run 151 |
| ❌ FAIL | 音頻峰值 audio_peak | -0.07 | <= -1.0 dBFS | clipping risk |
| ⏭️ SKIP | 字幕越界 subtitle_safe_area |  |  | no subtitle boxes supplied |
| ✅ PASS | 字體缺失 fonts | [] | all font files present | ok |
| ⏭️ SKIP | 人臉遮擋 face_occlusion |  |  | no overlay boxes supplied |

## 需要處理 Action items

- ❌ **音頻峰值 audio_peak**: clipping risk
- ⚠️ 重複幀檢測 duplicate_frames: 1925 duplicate frame(s), longest run 151（請人工確認 please confirm manually）
