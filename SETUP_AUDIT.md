# SETUP AUDIT · Cloud AI Video Production Studio

- 审计日期：2026-10-19（第二轮：网络放行后的新容器，09:20 UTC 启动）
- 环境：Claude Code 云端会话（Linux 6.18，4 CPU，16 GB RAM，无 GPU）
- 分支：`claude/cloud-ai-video-studio-setup-utp2z3`
- 重新审计：`studio audit`（JSON 输出；`--offline` 跳过网络检查）

> **结论：Setup 尚未全部完成。** 系统、渲染、QC、团队流程、Drive 公开读取、参考导入、风格分析、本地免费转写、Docker（CI）均已实测通过。Drive **输出目录**已由官方连接器建立于 yukikimchi2@gmail.com（`config/drive_output.yaml`），连接器上传读回文本 / 报告 / 825 B MP4 通过；但**正式体积影片经连接器交付 NOT PASS**（只能内嵌 base64），**无人值守上传 BLOCKED**（容器无 Google 身份）。Groq 转写 UNVERIFIED（可选）。风格档案全部待人工审核。原有三个 DFCC 文件夹为只读参考来源。在你确认之前，不会制作任何正式影片。
>
> 续接方式见 **[CONTINUE_SETUP.md](CONTINUE_SETUP.md)**。

---

## 1. 第一阶段：现有环境审计（15 项）

| # | 项目 | 发现 | 状态 |
|---|---|---|---|
| 1 | Claude Code 运行环境 | 云端会话，Python 3.13、4 CPU、16 GB | 已存在 · 可以继续使用 |
| 2 | 是否真正持久化 | **否**。云端容器是临时的，会话结束即回收。持久化改由 GitHub（代码/状态）+ Google Drive（影片）承担；环境可由 Dockerfile / devcontainer / SessionStart hook 重建 | 需要重新配置 → **已处理** |
| 3 | GitHub 连接 | 仓库可读写；已多次实际 push 到远端分支 | 已存在 · 可以继续使用 |
| 4 | Google Drive 连接 | **文件夹权限**：3 个均 anyone:writer（可写）。**Claude 端读取 ✅**（公开链接）。**Claude 端写入 ⛔**：无 Google 身份——官方 Google Drive 连接器 connect_incomplete、自订 drive 连接器 needs_reconnect、`CLOUDSDK_AUTH_ACCESS_TOKEN` 为无效占位值 | 读取可用 · Claude 端写入 BLOCKED（认证，非权限） |
| 5 | 云端 GPU | 无 GPU；未开通任何付费资源。改采免费优先：CPU 渲染 + Groq 免费 Whisper API + 本地 CPU + Kaggle 免费 GPU | 尚未安装 · **免费方案已接入** |
| 6 | Python | 3.13.16 | 已存在 · 可以继续使用 |
| 7 | FFmpeg / FFprobe | 6.1.1 | 已存在 · 可以继续使用 |
| 8 | Docker | 有 CLI，无常驻 daemon；本环境内无法解析 deb.debian.org，镜像构建改由 GitHub Actions `docker` job 验证 | 已存在 · 需要重新配置 → CI 验证 |
| 9 | 视频相关 Repository | 仅本仓库（初始只有 README） | 已存在 · 已建立系统 |
| 10 | 旧的视频剪辑项目 | 3 个参考文件夹内为 3 支已剪好的采访 Reel（2026-10-09 采访日）；无工程文件 | 已存在 · 作为参考（只读） |
| 11 | 现成 Motion Graphics 代码 | 无 → 已新建 `studio/motion/` | 尚未安装 → **已建立** |
| 12 | 以前的视频模板 | 无模板文件；从成片观察到固定元素（顶部绿色标签、姓名贴纸、绿色关键词字幕、云朵片尾） | 尚无 → 待确认后做成模板 |
| 13 | 团队共享素材库 | 只取得 3 个参考文件夹（他人 Drive，公开链接）；团队主素材库位置未提供 | 部分可访问 |
| 14 | 自动化工作流程 | 无 → 已建立 CI、渲染队列、SessionStart hook | 尚未安装 → **已建立** |
| 15 | 可重复使用品牌素材 | 你提供的 `DFSC_2027_Key_visual.ai` → 已提取为矢量 Logo（星芒、三色北极星、啟航字标、圓夢工場 Lockup、纸飞机）与色板 | 已存在 · 已整合 |

### 工具与套件

| 项目 | 版本 / 状态 |
|---|---|
| numpy / opencv-python-headless / pillow / scipy | 2.5 / **4.14（锁定 <5：OpenCV 5 移除了 Haar 人脸检测）** / 12.3 / 1.18 |
| faster-whisper | 1.2.1；large-v3-turbo 权重已下载到 workspace（`studio models fetch`）；音频改由 FFmpeg 解码（PyAV 19 与其不相容） |
| pymupdf / pyloudnorm / soundfile / opencc | 已安装 |
| google-api-python-client / google-auth / gdown / yt-dlp | 已安装 |
| 字体 | Noto Sans CJK TC / HK 全字重（`fonts-noto-cjk` + `fonts-noto-cjk-extra`）、Noto Color Emoji。**无 Apple Emoji、无 PingFang**（未假设其存在） |
| gcloud CLI | 已安装，未登录 |

### 网络可达性（第二轮实测，`workspace/logs/audit_*.json`）

| 主机 | 结果 |
|---|---|
| github.com、pypi.org、www.googleapis.com | 可达 |
| drive.google.com、drive.usercontent.google.com | ✅ 可达 |
| huggingface.co（模型 CDN 也可下载） | ✅ 可达（匿名下载曾被限流 429，自动等待后完成） |
| www.facebook.com、fb.watch | ✅ 可达 |
| www.notion.so、notion.site | ✅ 可达 |
| **app.notion.com、api.notion.com** | ⛔ 阻挡（属 notion.com，不在 notion.so 白名单）→ 改用同一页面 ID 走 www.notion.so，已成功 |
| api.groq.com | ✅ 可达（401 = 尚无 key） |
| www.kaggle.com、api.runpod.io | ⛔ 阻挡（目前不需要） |

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

## 3. 验收矩阵（第二轮，附日志）

日志在云端工作区 `workspace/logs/`（不进 git）；报告类成果已提交到 `projects/dfsc-2027/references/`。

| # | 验收项目 | 结果 | 证据 |
|---|---|---|---|
| 1 | Test 1 — Cloud Environment | ✅ PASS | 新容器 09:20 启动，SessionStart hook 自动装好套件与繁中字体 |
| 2 | Test 2 — GitHub 提交 / 读取 / 更新 / 恢复 | ✅ PASS | 测试 + 多次实际 push（最新 commit 见分支） |
| 3a | Test 3a — Drive **公开读取** | ✅ PASS | 3 文件夹列出（4 个文件）；3 支影片下载 134–194 MB，ffprobe / 完整解码通过；`test_3a_drive_public_read…` 通过 |
| 3b | **无人值守上传**（`studio drive check` / `studio queue run --upload`） | ⛔ **BLOCKED（容器无 Google 身份）** | 匿名上传 401；`studio drive check` exit 2。上传目标已设：`drive.previews_folder_id = 06_Project_Previews/dfsc-2027`。连接器授权不会进入容器；未提取 token、未建立密钥 |
| 3d | **对话连接器**：建立输出目录 + 上传 + 读回（文本 / 报告 / 极小二进制） | ✅ PASS | 建立 `Cloud Video Production Studio` 37 个目录（`config/drive_output.yaml`）；TXT 362 B、QC 报告 1485 B、PNG 79 B、**MP4 825 B（ffprobe h264 16×16 1 帧，逐字节相同）** 读回 MD5 全部一致 |
| 3f | **对话连接器：正式体积 MP4 交付** | ❌ **NOT PASS** | `create_file` 只接受内嵌 textContent/base64Content，无文件路径/URL/引用参数，读不到容器文件；大小上限未标示（UNVERIFIED）；4.9 KB MP4 的 base64 转录即失败。不可作为生产交付方案 |
| 3e | 对话连接器写入原有 DFCC 文件夹 | ⏸ 不需要 | 连接器只看得到自己建立的文件；原有三个文件夹改定位为**只读参考来源**，输出改用专用目录（3d） |
| 3c | 跨端上传可在 Claude 端读回 | ✅ PASS | ChatGPT 端连接器上传 `STUDIO_SETUP_WRITE_TEST_20261019.txt`（`1IxNFMiI…`）→ Claude 端列出并下载，198 bytes，MD5 `68a8b6de…`。**仅证明跨端可见，不代表 Claude pipeline 可上传** |
| — | 文件夹写入权限（ChatGPT 端实测） | ✅ 可写 | 3 个文件夹 permissions 含 `{type:anyone, role:writer}`；ChatGPT 端上传并回读成功（用户提供） |
| 4 | Facebook 参考 | ✅ PASS | 2 支下载（40.9s 竖屏、60s 横屏）+ 元数据 |
| 5 | Notion 参考 | ✅ PASS | 总页 + 4 个子页面导出（`references/notion/`） |
| 6 | 风格分析 | ✅ PASS（数据） · ⏳ 待审核 | 5 份报告、5 个 Ref 档案、2 个草稿档案，全部 UNREVIEWED；`STYLE_FINDINGS.md` |
| 7 | 本地 Whisper CPU 真实转写 | ✅ PASS | 57.9s 采访 → 30.7s（1.89× 实时），191 字词、繁体；`references/transcript_test_DFCC_YYLim.srt`；发现 1 处听写错误 |
| 8 | 真实素材 → 字幕 / 剪辑计划 / 选段 | ✅ PASS | 16 条字幕（≤14 字/行，无重叠）、SRT 读回、Hook/Storyline/Benefits/CTA 选段；修复选段重叠 bug |
| 9 | 人脸检测（真实画面） | ✅ PASS | 3 支影片 × 4 帧，12/12 检测到受访者（1 帧多检 1 个） |
| 10 | QC 引擎（真实成片） | ✅ PASS | 3 支参考成片正确判定：峰值削波、HEVC、重复帧（`references/qc_reference_videos/`） |
| 11 | Motion 模板 | ✅ PASS | 8 个模板全部重建预览 passed=True；金句卡引号重叠已修复（回归测试在旧代码失败、新代码通过） |
| 12 | 渲染 + QC（Final） | ✅ PASS | 合成测试卡 1080×1920 CRF16，实测 -14.06 LUFS / -12.4 dBTP，QC（含响度）PASSED |
| 13 | 全新环境交接 | ✅ PASS | 从 GitHub 重新 clone + 全新 venv 安装 → 199 passed / 2 skipped，CLI / 渲染 / QC 正常 |
| 14 | Groq 免费转写 | ⏸ **UNVERIFIED** | 网络可达，但无 `GROQ_API_KEY`（可选；模拟 API 测试通过） |
| 15 | Docker 镜像构建 | ✅ PASS（GitHub Actions） | CI run #9（commit `fe099a4`）`docker` job：Build studio image ✅ + Run audit inside the image ✅；`test` job ✅。run #5–#9 全部 success（#1–#4 test job 失败，已修复） |
| 16 | 自动测试总数 | ✅ 见下方最新执行 | 跳过：无人脸后端情境、卡通测试图、Claude 端 Drive 写入（BLOCKED） |

未执行：正式影片（按指示）、付费 GPU、排程任务、任何 Drive 写入或删除。

## 4. 仍需要人处理

| # | 项目 | 说明 |
|---|---|---|
| 1 | 正式影片交付 | 连接器无法交付 MB 级影片（3f）。择一：A）在环境设定提供容器 Google 身份（yukikimchi2@gmail.com 的 `STUDIO_DRIVE_TOKEN`，或服务账号并把输出目录共享给它）→ `studio queue run --upload` 自动上传到 `06_Project_Previews/dfsc-2027`；B）人工从云端工作区下载影片后上传。小文件（QC 报告、字幕、交接文件）可由 Claude 经连接器上传（3d） |
| 2 | 风格决策 | 回答 `projects/dfsc-2027/references/STYLE_FINDINGS.md` 第 7 节（繁/简字幕、圆梦口号、固定品牌元素、3 支采访是否为已审核版本） |
| 3 | 审核 | Reviewer 审核 `DFSC_Interview_Reel`、`DFSC_Launch_Cinematic`、`dfsc2027_north_star_open` |
| 4 | Groq（可选） | 若要更快的免费转写：在环境设定加入 `GROQ_API_KEY`（音频会上传给 Groq 处理） |
| 5 | Notion 链接 | 若希望直接用 `app.notion.com` 链接，需把 `notion.com` 子域加入白名单；目前已用 notion.so 绕行成功 |
| 6 | 字体 | 确认 Noto Sans CJK HK 替代 PingFang HK |

### GPU：免费优先

渲染、Motion Graphics、QC 全部 CPU 免费运行；转写用本地 CPU（已实测 1.9× 实时）→ Groq 免费 API（可选）→ Kaggle 免费 GPU（大批量时）。`gpu.provider: none`，付费守门机制保留。详见 `docs/zh/08_云端GPU评估与成本.md`。

## 5. 已知限制

- 渲染为 CPU（NumPy/OpenCV）：540×960 约 0.05 秒/帧，1080p 约慢 3–4 倍。60 秒 Final 约数分钟。
- 说话者分段为停顿/能量启发式（2 人），非真正 diarization；可之后接 pyannote（需 Hugging Face）。
- 人脸检测为 OpenCV Haar（侧脸较弱；真实画面 12 帧中 1 帧多检一个）；可放入 YuNet 模型（`STUDIO_YUNET_MODEL`）提升。
- 风格分析的字幕位置检测在真实采访上不可靠（报告 0.40 高度，目测约 0.75–0.80），以人工判断为准。
- Whisper 转写需人工校对（专有名词、同音字）。
- 参考影片、Whisper 模型存在临时工作区，新容器需重新取得（`studio references ingest`、`studio models fetch`）。
- 画面文字检测对浅色复杂背景上的字幕会漏判；BPM 估计复杂音乐可能差一个八度。
- Glass Panel 在卡片缩放/旋转时模糊区域不随之变形。
- 7 个初始风格档案只是**类别占位**；真实分析档案（Ref_* 与 2 个草稿）全部 UNREVIEWED。
