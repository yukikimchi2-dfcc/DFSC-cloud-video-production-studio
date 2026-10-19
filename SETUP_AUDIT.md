# SETUP AUDIT · Cloud AI Video Production Studio

- 审计日期：2026-10-19
- 环境：Claude Code 云端会话（Linux 6.18，4 CPU，16 GB RAM，无 GPU）
- 分支：`claude/cloud-ai-video-studio-setup-utp2z3`
- 重新审计：`studio audit`（JSON 输出；`--offline` 跳过网络检查）

> **结论：Setup 尚未全部完成。** 代码系统、渲染、测试、团队流程已可用。你已允许所需网域，但需在**新会话**中生效；Drive 写入、Groq 转写还需要凭证（见第 4 节）。在你确认之前，不会制作任何正式影片。

---

## 1. 第一阶段：现有环境审计（15 项）

| # | 项目 | 发现 | 状态 |
|---|---|---|---|
| 1 | Claude Code 运行环境 | 云端会话，Python 3.13、4 CPU、16 GB | 已存在 · 可以继续使用 |
| 2 | 是否真正持久化 | **否**。云端容器是临时的，会话结束即回收。持久化改由 GitHub（代码/状态）+ Google Drive（影片）承担；环境可由 Dockerfile / devcontainer / SessionStart hook 重建 | 需要重新配置 → **已处理** |
| 3 | GitHub 连接 | 仓库可读写；已多次实际 push 到远端分支 | 已存在 · 可以继续使用 |
| 4 | Google Drive 连接 | 无凭证、无 Drive 连接器。Drive **API**（googleapis.com）网络可达；`drive.google.com` 网页链接被网络策略阻挡 | **无法访问**（需授权） |
| 5 | 云端 GPU | 无 GPU；未开通任何付费资源。改采免费优先：CPU 渲染 + Groq 免费 Whisper API + 本地 CPU + Kaggle 免费 GPU | 尚未安装 · **免费方案已接入** |
| 6 | Python | 3.13.16 | 已存在 · 可以继续使用 |
| 7 | FFmpeg / FFprobe | 6.1.1 | 已存在 · 可以继续使用 |
| 8 | Docker | 有 CLI，无常驻 daemon；本环境内无法解析 deb.debian.org，镜像构建改由 GitHub Actions `docker` job 验证 | 已存在 · 需要重新配置 → CI 验证 |
| 9 | 视频相关 Repository | 仅本仓库（初始只有 README） | 已存在 · 已建立系统 |
| 10 | 旧的视频剪辑项目 | 仓库内无；Drive 内可能有，但**无法访问** | 无法访问 |
| 11 | 现成 Motion Graphics 代码 | 无 → 已新建 `studio/motion/` | 尚未安装 → **已建立** |
| 12 | 以前的视频模板 | 仓库内无；Drive 内未知 | 无法访问 |
| 13 | 团队共享素材库 | 未知（Drive 无法访问） | 无法访问 |
| 14 | 自动化工作流程 | 无 → 已建立 CI、渲染队列、SessionStart hook | 尚未安装 → **已建立** |
| 15 | 可重复使用品牌素材 | 你提供的 `DFSC_2027_Key_visual.ai` → 已提取为矢量 Logo（星芒、三色北极星、啟航字标、圓夢工場 Lockup、纸飞机）与色板 | 已存在 · 已整合 |

### 工具与套件

| 项目 | 版本 / 状态 |
|---|---|
| numpy / opencv-python-headless / pillow / scipy | 2.5 / **4.14（锁定 <5：OpenCV 5 移除了 Haar 人脸检测）** / 12.3 / 1.18 |
| faster-whisper | 1.2.1 已安装（模型权重无法下载，见阻碍 #2） |
| pymupdf / pyloudnorm / soundfile / opencc | 已安装 |
| google-api-python-client / google-auth | 已安装 |
| 字体 | Noto Sans CJK TC / HK 全字重（`fonts-noto-cjk` + `fonts-noto-cjk-extra`）、Noto Color Emoji。**无 Apple Emoji、无 PingFang**（未假设其存在） |
| gcloud CLI | 已安装，未登录 |

### 网络可达性（本云端环境的网络策略）

| 主机 | 结果 | 影响 |
|---|---|---|
| github.com、pypi.org | 可达 | — |
| www.googleapis.com（Drive API） | 可达（401 = 需要凭证） | 只差凭证 |
| drive.google.com | 阻挡 | 只影响网页链接，不影响 API |
| huggingface.co | 阻挡 | **Whisper 模型无法下载** |
| app.notion.com / www.facebook.com | 阻挡 | 参考资料无法读取 |
| api.runpod.io | 阻挡 | 目前不需要（未批准 GPU） |

---

## 2. 已建立的系统

| 阶段 | 内容 | 状态 |
|---|---|---|
| 二 · Cloud Workspace | GitHub 仓库结构、`Dockerfile`（CPU / GPU 双用）、`.devcontainer/`（Codespaces，密钥自动写入 `secrets/`）、`.claude/hooks/session-start.sh`（新的云端会话自动安装字体与套件）、GitHub Actions CI（测试 + 测试渲染 + QC + 镜像构建） | ✅ 完成（镜像构建待 CI 首次执行确认） |
| 三 · Google Drive 素材系统 | `studio/storage/`：Drive（断点续传、MD5 校验、不删除、同名不覆盖）、本地后端、「先找再建」文件夹结构、增量分批素材索引（来源/ID/版本/MD5/用途/品牌/审核状态） | ✅ 代码完成并测试 · ⛔ 真实 Drive 待授权 |
| 四 · 风格分析 | `studio/style/`：镜头、剪辑频率、节奏曲线、前三秒 Hook、运镜、字幕区域、色彩、对比、饱和度、BPM、片头片尾；风格档案 APPROVED / REFERENCE_ONLY / REJECTED / UNREVIEWED + 审核历史 | ✅ 引擎完成 · ⛔ 尚未分析任何真实影片（素材在 Drive） |
| 五 · Motion Graphics Engine | 文字（繁中/英文、逐字弹跳/飞入/砸落/扫光/遮罩/竖排…）、9 种卡片、运镜（含人脸追踪）、10 种转场（帧数控制）、粒子/星芒/色散/暗角/光晕、贴纸（Noto Emoji）、8 个模板（含 `dfsc2027_north_star_open`，UNREVIEWED） | ✅ 完成 |
| 六 · AI 剪辑引擎 | 转写（Whisper large-v3-turbo、逐字时间码、语气词、说话者分段）、目标导向选段 → EDL（保留原片时间码）、删停顿/语气词 + 误删验证、自动竖屏、字幕（逐字高亮、SRT/ASS、可人工修改后读回）、音频（降噪/EQ/压缩/LUFS/Ducking/交叉淡化）、QC | ✅ 完成 · ⛔ 转写需模型权重 |
| 七 · 自动渲染 | Preview（720×1280、≤30 MB 自动调整）/ Final（1080×1920、CRF 16、AAC 256k、-14 LUFS / -1.5 dBTP 两段式），队列 + 重试 + 日志 + 分段缓存 + 局部重渲 + 版本记录，**永不覆盖** | ✅ 完成 |
| 八 · 团队协作 | 角色权限与状态流程（`config/roles.yaml`，系统强制）、`activity.jsonl`、自动 `HANDOVER.md`、中文文档 | ✅ 完成 |
| 九 · 自动测试 | 201 个测试 | ✅ 见第 3 节 |

DFSC 2027 品牌包：`projects/dfsc-2027/brand/brand.yaml` —— 设计师确认色 green `#47B649`、blue `#1C61AE`、black K100（导出为 `#231F20`）；字体以 Noto Sans CJK **HK** 替代 PingFang HK；Motion 规则为**提议、未审核**。

---

## 3. 测试结果（`python3 -m pytest -m "not network"`）

**197 passed · 2 skipped · 2 deselected（network）**，约 20 秒。

| 测试 | 结果 |
|---|---|
| Test 1 — Cloud Environment | ✅ 在云端会话中运行；FFmpeg、繁中字体、所有套件到位 |
| Test 2 — GitHub | ✅ 提交 / 读取旧版本 / 更新 / revert 恢复（临时 clone）；✅ 实际 push 到远端分支 |
| Test 3 — Google Drive | ⛔ **BLOCKED**（无凭证）。相同的读/写/下载/MD5 逻辑已用本地后端验证通过 |
| 渲染 | ✅ Preview 版本递增与记录、Final 响度实测 -14 ±1 LUFS / 真峰值 ≤ -1 dBTP、30 MB 上限自动调整、局部渲染 |
| 队列 | ✅ 失败重试 + 日志、分段缓存、只重渲被修改的段落、新版本不覆盖旧版本 |
| QC | ✅ 每个检测器都能抓到注入的瑕疵（黑帧、冻结帧、峰值、LUFS、格式、字幕越界、人脸遮挡、字体缺失），且干净素材通过 |
| Motion / 模板 | ✅ 8 个模板全部可建构与渲染；繁中字形非空；**字体使用 TC/HK 而非简体 SC**（回归测试） |
| 跳过 | 1) 转写真实模型（权重无法下载）2) 人脸检测对卡通测试图不触发（需要真人照片验证） |

合成测试影片（全部标记「TEST · 合成測試素材」）：测试卡、8 个模板预览（`templates/*/preview.gif`）、7.8 秒 Motion 测试 reel。未使用任何真实采访素材，未覆盖或删除任何旧影片。

---

## 4. 阻碍与需要你做的事（2026-10-19 更新）

你已在环境设定中允许 Google Drive、Notion、Facebook、huggingface.co。**但本会话的容器是在修改前启动的**，代理仍然拒绝这些网域（实测 403 policy denial）。网络设定在新会话启动时读取，所以下列工作要在**新会话**中完成。

### 4.1 新会话需要允许的完整网域清单

| 用途 | 网域 |
|---|---|
| Google Drive 公开文件夹读取 / 下载 | `drive.google.com`、`drive.usercontent.google.com`、`docs.google.com` |
| Whisper 模型权重 | `huggingface.co`、`*.hf.co`（如 `cdn-lfs.hf.co`） |
| Notion | `app.notion.com`、`www.notion.so`、`api.notion.com` |
| Facebook 影片 | `www.facebook.com`、`facebook.com`、`*.fbcdn.net` |
| 免费 Whisper API | `api.groq.com` |
| 免费 GPU（大批量时） | `www.kaggle.com` |

### 4.2 新会话的执行清单（交给 Claude 执行即可）

```bash
studio audit                                   # 确认上述网域都 reachable
studio references ingest dfsc-2027             # 读取三个 Drive 文件夹 + 两支 Facebook 影片 → 风格报告 + UNREVIEWED 风格档案
python3 -m pytest -q                           # 含转写真实模型测试
```
并读取 Notion 页面，把品牌 / 大赛资料整理进 `projects/dfsc-2027/`。

### 4.3 仍需你提供的东西

| # | 项目 | 为什么 | 怎么做 |
|---|---|---|---|
| 1 | Drive 文件夹共享方式 | 「允许网域」只解决网络。**公开**（知道链接者可查看）的文件夹可直接读取；私人文件夹或要**写入/上传**成品，需要凭证 | 读取：把三个文件夹设为「知道链接的任何人可查看」。写入：建立服务账号金钥放进 `STUDIO_DRIVE_CREDENTIALS_JSON`（`docs/zh/03_Google_Drive_连接.md`），或在 https://claude.ai/customize/connectors 连接 Google Drive |
| 2 | Notion 页面权限 | 私人页面需要授权 | 页面「Share → Publish to web」，或连接 Notion 连接器，或建立 Notion integration 并把 token 放进 `NOTION_TOKEN` |
| 3 | Facebook 影片 | 须为公开贴文 | 若为私人/社团内容，请把影片文件直接放进 Drive `03_Style_References/` |
| 4 | Groq 免费 API key（推荐） | 免费转写主力，不需要 GPU | https://console.groq.com/keys 免费注册 → 环境密钥 `GROQ_API_KEY` |
| 5 | 风格与模板审核 | 风格档案必须人工批准 | 审核 `templates/dfsc2027_north_star_open/preview.gif` 与 `brand.yaml` 的 motion 提议；指定 Reviewer |
| 6 | 字体授权 | PingFang HK 无服务器授权 | 确认用 Noto Sans CJK HK，或提供授权字体 |

### 4.4 GPU：已改为免费优先方案

不再建议任何付费 GPU。渲染、Motion Graphics、QC 全部在 CPU 上免费运行；只有转写受益于 GPU，改用：
① **Groq 免费 Whisper API**（已接入代码，`transcription.backend: auto`，每天约 8 小时音频免费）→ ② **本地 CPU**（机密素材）→ ③ **Kaggle 免费 GPU**（每周约 30 小时，大批量时）。
详见 `docs/zh/08_云端GPU评估与成本.md`。付费 GPU 守门机制保留，`gpu.provider: none`。

## 5. 已知限制

- 渲染为 CPU（NumPy/OpenCV）：540×960 约 0.05 秒/帧，1080p 约慢 3–4 倍。60 秒 Final 约数分钟。
- 说话者分段为停顿/能量启发式（2 人），非真正 diarization；可之后接 pyannote（需 Hugging Face）。
- 人脸检测为 OpenCV Haar（侧脸较弱）；可放入 YuNet 模型（`STUDIO_YUNET_MODEL`）提升。
- 画面文字检测对浅色复杂背景上的字幕会漏判；BPM 估计复杂音乐可能差一个八度。
- Glass Panel 在卡片缩放/旋转时模糊区域不随之变形。
- 金句卡开头引号「 与第一个字略有重叠（模板 `quote_card`，待修）。
- 7 个初始风格档案只是**类别占位**，没有任何分析数据，全部 UNREVIEWED。
