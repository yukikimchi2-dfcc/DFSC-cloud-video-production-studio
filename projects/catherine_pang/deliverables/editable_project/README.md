# 可編輯工程 — Catherine Pang · 洪記糖水 · 第九屆參賽者

成片 `Final_Edit.mp4` 由下面這些**獨立圖層**組成。字幕、Logo、標題、片尾都可以單獨替換，提供三種用法：

| 用法 | 適合 | 可改的東西 |
|---|---|---|
| **A. ChatCut 工程**（已建好，線上直接編輯） | 日常改字幕、改標題文字、換 Logo、換片尾 | 全部（標題是可編輯的 Motion Graphic） |
| **B. 剪映 / CapCut / Premiere / 達芬奇**：按圖層表手動疊層 | 想在剪映裡繼續精修 | 全部（標題是帶透明通道的獨立片段，可刪、可換、可挪） |
| **C. 自動重建**（`build.sh`） | 改剪輯內容或改很多標題，一鍵重出成片 | 全部，含剪輯點、配樂、音效 |

---

## A. ChatCut 工程

**連結：** https://app.chatcut.io/editor/484aed49-2663-4f8e-bef8-fd3d60ad5679
（工程名「Catherine Pang · 洪記糖水 · 第九屆參賽者」，結構與 Nelson Chin 工程一致）

時間線「**可編輯版（A-roll＋字幕＋片尾）**」：

| 軌道 | 內容 | 怎麼改 |
|---|---|---|
| V1 | `CatherinePang_A-roll_無字卡.mp4`（構圖、推拉、轉場特效、完整聲音，**無任何文字**）→ 6 幀叠化 → `DFSC_品牌片尾_第十一屆.mp4` | 換片尾：刪掉片尾片段，把新片尾拖到同一位置 |
| V2 | `dreamfactory_watermark.png`（左上角 Logo，x 32 / y 59 / 寬 177） | 換 Logo：上傳新 PNG，替換此片段 |
| V3–V5 | 41 個「**DF標題卡（可編輯）**」Motion Graphic | 點選後在屬性面板改：**文字**（`[ ]` 內為綠色關鍵詞）、**樣式**（深藍框 / 綠框 / 白標籤 / 白色襯線大字 / 綠色襯線大字）、**字號**、**左右 emoji 貼紙**、**退場幀**（等於片段長度，改片段長度時一併修改） |
| 字幕 | ChatCut 字幕（50 張卡，已改為繁體、修正錯字、關鍵詞綠色 `#68D468`） | 在字幕面板直接改字；字體 Noto Sans TC 700、64px、白色 `#F9FAFC`、6px 深色描邊 |

時間線「**成片 v001（參考，含字卡）**」放的是最終成片，用於對照。

> ChatCut 字幕位置已設為比預設上移 8%（約 156 px），對應視頻 1 的字幕中心 y ≈ 1300。這一步沒能在 ChatCut 預覽中截圖核對，打開工程時請看一眼；需要的話直接拖動字幕框即可。

---

## B. 剪映 / CapCut / Premiere / 達芬奇：圖層表

畫布 **1080 × 1920，23.976 fps**（剪映選 9:16、幀率 23.976 或 24 均可）。所有素材都在本資料夾的上一層 `deliverables/`。

| 層 | 檔案 | 放置 |
|---|---|---|
| 1 主畫面 | `CatherinePang_A-roll_無字卡.mp4` | 00:00:00 開始，全屏，長度 73.07 s（自帶完整混音：人聲＋配樂＋音效） |
| 2 片尾 | `DFSC_品牌片尾_第十一屆.mp4` | 接在主畫面後（01:13.07），兩段之間加 0.25 s「叠化」轉場 |
| 3 Logo | `Logo_Transparent_White.png` | 0 – 73.07 s；寬 172 px，左上角距左 35 px、距上 62 px（以畫布左上角為原點） |
| 4 標題 | `editable_project/titles/*.mov`（38 段，透明背景，全幅 1080×1920，**放進去即在正確位置**） | 按 `titles/titles_timecodes.csv` 的開始時間放到時間線上（第 2 欄是 23.976 fps 的幀號，第 4 欄是 分:秒） |
| 5 字幕 | `Subtitle.srt`（繁體，與畫面同步） | 剪映：文本 → 本地字幕 → 導入 SRT；樣式見下 |
| 音軌（可選） | `stems/speech_proc.wav`、`stems/bgm.wav`、`stems/sfx.wav` | 想單獨調音量時：把主畫面靜音，三條音軌都從 00:00:00 放入 |

**字幕樣式（對照視頻 1）：** 字體 思源黑體 / Noto Sans TC 粗體；字高約 64 px（約畫面寬 6%）；顏色 `#F9FAFC`；深色描邊 `#0C0E14`；黑色柔和陰影約 55%；單行居中，中心高度 y ≈ 1300 px（畫面高度約 68% 處）；關鍵詞改綠色 `#68D468`。`Subtitle.ass` 已包含上述完整樣式，Premiere、達芬奇、Aegisub 可直接讀取。

**標題片段：** 每段都是 PNG 編碼、帶 Alpha 的 MOV，可直接刪除、替換或移動。如果剪映版本讀不到 MOV 的透明通道，可以用 ChatCut（方法 A）改標題，或用方法 C 重出。

**其他交換格式：**
- `Timeline.fcpxml` — Final Cut Pro / 達芬奇：A-roll 剪輯點（指向原始素材，起始時碼 22:25:36:12）＋片尾＋Logo＋配樂＋音效。打開後把 `file:///RELINK/...` 重新連結到本地檔案。
- `Edit_Decision_List.edl` — CMX3600，Premiere / 達芬奇 / Avid 可讀。
- `cut_list.csv`、`graphics_cues.csv` — 每個剪輯點、每個標題的時間碼表。

> 剪映工程檔（draft_content.json）在新版本中是加密格式，無法可靠地從外部生成，所以這裡提供的是剪映能直接讀取的獨立圖層與 SRT。

---

## C. 一鍵重建（改完自動出新成片）

```bash
RAW=原始採訪.mp4 REF=參考視頻1.mp4 bash projects/catherine_pang/build.sh
```

| 想改 | 改哪裡 |
|---|---|
| 字幕文字 / 關鍵詞 / 保留哪些句子 / 句子順序 | `projects/catherine_pang/plan.py`（`text` = 字幕，`kw` = 綠色關鍵詞，`say` = 保留的原話） |
| 標題文字、樣式、emoji、出現時間 | `projects/catherine_pang/titles.py`（時間綁定在說話的字上，剪輯改了也會自動對齊） |
| Logo | `LOGO=新Logo.png bash build.sh`，或替換 `projects/catherine_pang/assets/Logo_Transparent_White.png` |
| 片尾 | `OUTRO=新片尾.mp4 bash build.sh`（片尾檔從第一幀開始即可，會自動做 0.25 s 叠化） |
| 只重出畫面，不重剪 | `FROM=4 bash build.sh`（只重做標題/字幕/Logo/片尾） |

輸出會重新生成到 `deliverables/`：成片、無字卡 A-roll、SRT/ASS、標題透明片段、時間碼表、EDL/FCPXML、音軌。
