# 采访 Reel · Nelson Chin · 五告凉 · 第十屆參賽者

| 项目 | 内容 |
|---|---|
| 素材 | `9Oct_凉茶_0050.MP4`（Drive `1Wa3MwPiNKw12j3q6i7C5DUBeIgqH6v3X`，1728×3072 HEVC 59.94 fps，107 s，第一条音轨 = 手持麦）——只读，未修改 |
| 风格 | `DFSC_Interview_Reel`（REFERENCE ONLY），对齐同日成片 `DFCC_9Oct_JoshuaChin_SmartRental`、`DFCC_9Oct_ChiliAng_Eggteen` |
| 输出 | 1080×1920 · 59.94 fps（同素材）· H.264 High / AAC 256k · −14 LUFS / ≤ −1.5 dBTP · 约 65 s |
| 重剪 | `python3 projects/dfsc-2027/edits/nelson_chin_gaochill/edit.py --source <素材> --outro-ref <ChiliAng 成片>`（`--preview` 出 720p） |

剪辑点、字幕、字卡全部写在 `edit.py` 的 `RANGES` / `CUES` / `OVERLAYS`（素材时间），改数字重跑即可；输出按 `_v###` 递增，不覆盖。

## 结构（剪辑 SOP §4 单人故事 Reel + 参考成片）

| 段落 | 内容（受访者原话） | 字卡 |
|---|---|---|
| 钩子 0:00 | 可是我沒有想到，我踏上了這條不歸路，反而更累 | 问题条「創業還是打工？」+ 小标「沒想到」+ 红色大字「不歸路」 |
| 自我介绍 | 我在賣涼茶，我賣五告凉涼茶，100%天然食材，沒有加糖 | 姓名牌 **Nelson Chin** 👋🍵 + 「五告凉 · 第十屆參賽者」；绿卡「100%天然 · 沒有加糖」 |
| Q 為什麼選擇創業 | 時間比較 flexible…可是沒想到…反而更累 | 「時間比較flexible」⏰、大字「反而更累」😩 |
| Q 夢想從什麼時候開始 | 一年半前；逛市集看到糖分高、不養生 → 看到商機，做了這款涼茶 | 「一年半前」「逛市集」「糖分比較高」「看到這個商機」 |
| Q 第一筆啟動資金 | 差不多 8000 塊左右 | 大字「8000塊」💰 |
| Q 剛開始創業做什麼行業 | 也是在創業；before 做涼茶，開 marketing agency，做 branding、設計 | 「Marketing Agency」「Branding · 設計」 |
| Q 現在還在做嗎 | 還在做著；涼茶成功 → 變正職，agency 變 part time，希望 | 「涼茶 → 正職」「Agency → Part time」 |
| 最后一题 Q 有人給你100千 | 投我涼茶吧，五告凉涼茶 | 绿色大字「投我涼茶吧」🔥 |
| 片尾 | 品牌片尾（第十一屆三個賽道 → 雲朵 → 圓夢工場·創業大賽 卡），直接取自 ChiliAng 60.70–69.67，与 JoshuaChin 42 s 起相同 | — |

删除的内容：采访者口头提问（改为字卡，如参考片 JoshuaChin 0:25「拿到100千 第一步?」）、「為什麼我會開始這個呢」+ 第一次说一半的市集句（他随后完整重讲）、两次「before 我做這個涼茶，我是做/開…」口误重来、结尾「好，謝謝你」。

## 元素 ↔ 参考来源

| 元素 | 参考（文件 · 时间码） |
|---|---|
| 左上 dream factory 水印 | JoshuaChin / ChiliAng 全片；标志由 ChiliAng 68.5 s 片尾卡（已知底色 #EDEDED）抠出 → `brand/logos/dreamfactory_watermark.png`（白字版）、`dreamfactory_logo_light.png`（原色） |
| 问题条（深色半透明 + 绿框 + 绿点） | JoshuaChin 0:00.6「創業成功，到底有多難？」 |
| 小标 + 大标（深蓝 / 绿色，emoji） | JoshuaChin 0:10–0:35、ChiliAng 0:33「唯獨你站出來 / 接觸更多的世界」 |
| 红色大字钩子 | JoshuaChin 0:00「九死一生！」 |
| 黑色衬线大字 | ChiliAng 0:04「只有想法」 |
| 姓名牌 + 公司 · 身份 | JoshuaChin 0:03「Smart Rental · 圓夢工場導師」、ChiliAng 0:06「Eggteen 創辦人 · 二代創業」 |
| 字幕（白字黑边，绿色关键词底线，繁体） | 三支参考全片；y≈1400（JoshuaChin 同为手持麦街访，字幕在 0.73–0.76 高度） |
| 跳剪交替推近 1.14× | JoshuaChin 0:40 近景 / 中景交替 |
| 白闪转场 | ChiliAng 59.17–59.37 |
| 片尾溶接 0.12 s | ChiliAng 60.58–60.70 |
| 音乐 | 参考片讲话段无背景音乐，音乐只在品牌片尾（频谱比对）→ 本片同样处理 |

## 需要确认

1. **公司名写法**：产品与 T 恤 logo 写「五告凉」（两点水），字幕与姓名牌保留此写法；其余字幕为繁体（涼茶）。
2. **「100千」**：受访者原话；参考片 JoshuaChin 字卡同样写「100千」。
3. 片尾沿用参考片的第十一屆品牌片尾；受访者是第十屆參賽者，姓名牌已注明。
4. 圆梦口号 / 活动邀请：SOP 仍为【待定】，参考成片也未使用，本片未加。
