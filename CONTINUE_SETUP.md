# 续接 Setup（给下一个会话 / 下一位成员）

> 最后更新：2026-10-19 · 阶段：**Setup 可交接（仍有 BLOCKED 项）· 正式剪辑须有具体 brief + 指定素材**
> 持久规则：根目录 [CLAUDE.md](CLAUDE.md)（新会话自动读取）
> 完整审计与验收矩阵：[SETUP_AUDIT.md](SETUP_AUDIT.md)

## 1. 位置

| 项目 | 值 |
|---|---|
| 仓库 | https://github.com/yukikimchi2-dfcc/DFSC-cloud-video-production-studio |
| 分支 | `claude/cloud-ai-video-studio-setup-utp2z3`（全部系统与规则都在此分支；默认分支 `main` 只有 Initial commit，未合并，见 draft PR） |
| 云端环境 | Default（`env_01YZBZzYR4G41RjEdnZeQepN`），Network access = Limited + Allowed domains |
| 项目 | `projects/dfsc-2027/`（第十一屆 圓夢工場。創業大賽 2027 — 啟航 北極星） |

## 2. 参考链接

| 类型 | 链接 | 读取方式 | 状态 |
|---|---|---|---|
| Drive 素材 1 · DFCC_9Oct_JoshuaChin_SmartRental | https://drive.google.com/drive/folders/1oBLTdKEbSDsTX1ozQten90vS0M3rkMdo | anyone:writer；Claude 端公开读取 | ✅ 已读取 |
| Drive 素材 2 · DFCC_9Oct_YYLim_QJoyBalloon | https://drive.google.com/drive/folders/1x4YaQ1NOiW04Wnb_kM-N8N-1uT1sykG8 | anyone:writer | ✅ |
| Drive 素材 3 · DFCC_9Oct_ChiliAng_Eggteen_final(1) | https://drive.google.com/drive/folders/1kTg7UlLSuAaACuja_tVFHJ-uF571bYJ2 | anyone:writer | ✅ |
| 跨端测试文件（ChatGPT 端上传） | https://drive.google.com/file/d/1IxNFMiIqOjUCycT_hv54nZAZ1eFnn5Sp/view | Claude 端可读回 | ✅ |
| Notion | https://app.notion.com/p/Dreamfactory-3f14ddbea63a8022a1f1e3d4c4d1b038 | `app.notion.com` 被挡 → 用同一页面 ID 走 `www.notion.so` | ✅ 已导出 `projects/dfsc-2027/references/notion/` |
| Facebook 1 | https://www.facebook.com/share/r/1CL7DzWC9D/ | yt-dlp | ✅ |
| Facebook 2 | https://www.facebook.com/share/v/1DSeQULbZm/ | yt-dlp | ✅ |

## 3. 团队启动（每位成员每次开新会话）

**同一个 group / 组织不会自动继承规则**：新会话不共享任何对话或文件系统，只取得所选仓库分支中**已 push** 的文件，以及所选环境的 secret 和网络设定。规则会生效，是因为所选分支里有 `CLAUDE.md`。

| 选项 | 必须选择 |
|---|---|
| Repository | `yukikimchi2-dfcc/DFSC-cloud-video-production-studio` |
| Branch | `claude/cloud-ai-video-studio-setup-utp2z3`（PR 合并前**不要**选 `main`，`main` 里没有系统和规则） |
| Environment | Default（Network access = Limited + Allowed domains；Drive OAuth secret 设定后也在这里） |
| Connector | 确认会话工具中有 **ChatCut**（Claude 网页 Custom Connector，由宿主注入；不用装桌面插件、不提取 token）；如提示鉴权缺失，在 Claude 网页重新连接 ChatCut |

第一条指令（贴进新会话）：

> 先读 CLAUDE.md、CONTINUE_SETUP.md、SETUP_AUDIT.md 与 projects/dfsc-2027/HANDOVER.md，执行 `studio audit`，回报当前分支、最新 commit 与 BLOCKED 项目。没有我给的具体剪辑 brief 和指定素材，不开始正式剪辑。

简短启动说明（同一 group 的新 Cloud 会话）：
1. 选对 Repository、Branch（`claude/cloud-ai-video-studio-setup-utp2z3`）、Environment = Default。
2. 确认 ChatCut connector 在工具列表中（可只读调用 `list_projects` 验证）。
3. 先读 `CLAUDE.md`，再读本文件与 `SETUP_AUDIT.md`。
4. 新 ChatCut 项目 / 正式剪辑仍须用户明确指定素材与剪辑 brief；不擅自创建项目、导入、生成或消耗积分。

团队共用同一账号，用户不要求配置成员权限（GitHub 协作者、`config/team.yaml`、Drive 共享），**不作为阻碍**。

## 3b. 新容器开工（复制执行）

云端容器是临时的：`workspace/`（下载的参考影片、Whisper 模型、渲染）**不会保留**，需要时重新取得。

```bash
cd /home/user/DFSC-cloud-video-production-studio        # 或 git clone 上面的仓库 + 分支
git checkout claude/cloud-ai-video-studio-setup-utp2z3 && git pull
pip install -r requirements.txt && pip install -e .      # SessionStart hook 通常已自动完成
studio audit                                             # 确认网络：drive / huggingface / facebook / notion.so 应为 reachable
python3 -m pytest -q -m "not network"                    # 基线测试
studio models fetch                                      # 本地 Whisper（1.6 GB，约 4 分钟；HF 可能先限流 3 分钟）
studio references ingest dfsc-2027                       # 重新下载参考影片到 workspace（报告已在 git，不会覆盖已审核档案）
python3 -m pytest -q                                     # 含 network 测试（Drive 公开读取 3a、跨端回读 3c、真实转写）
studio drive check --folder 1oBLTdKEbSDsTX1ozQten90vS0M3rkMdo   # 3b：有 Claude 端 Google 身份后才会通过
python3 tools/notion_public.py "https://app.notion.com/p/Dreamfactory-3f14ddbea63a8022a1f1e3d4c4d1b038" \
        projects/dfsc-2027/references/notion/dreamfactory.md --subpages   # Notion 有更新时
```

## 4. 任务状态

| 任务 | 状态 |
|---|---|
| 环境审计、代码系统、渲染、QC、团队流程、中文文档 | ✅ 完成 |
| Drive **公开读取**（3 个文件夹，原公开链接） | ✅ 验收通过 |
| Drive 文件夹写入权限 | ✅ anyone:writer；ChatGPT 端上传 + 回读成功（用户提供证据） |
| ChatGPT 端上传文件在 Claude 端读回（3c） | ✅ |
| **Drive 输出目录** | `Cloud Video Production Studio`（yukikimchi2@gmail.com，ID 清单 `config/drive_output.yaml`）；Preview → `06_Project_Previews/dfsc-2027`，QC → `08_QC_Reports/dfsc-2027` |
| 对话连接器：建目录 / 上传读回文本、报告、极小 PNG 与 825 B MP4（3d） | ✅ PASS |
| 对话连接器：正式体积 MP4 交付（3f） | ❌ NOT PASS：只能内嵌 base64，不能引用容器文件 |
| 原有三个 DFCC 文件夹 | 只读参考来源（容器公开链接读取）；不写入 |
| 无人值守上传（3b） | ⛔ BLOCKED：等待一次浏览器 OAuth 授权；代码与配置清单已就绪（`docs/zh/04_Drive_OAuth_自动上传.md`） |
| 大文件上传器协议（3g，本地模拟端点） | ✅ 26 MB 中断续传 + MD5 + 解码（非 Google） |
| Docker 镜像（CI） | ✅ PASS：GitHub Actions `docker` job |
| Facebook / Notion 参考导入 | ✅ |
| 风格分析（5 支）+ 草稿档案 | ✅ 完成；`DFSC_Interview_Reel` / `DFSC_Launch_Cinematic` → REFERENCE_ONLY（用户授权成片为基准） |
| DFSC 两套模板（采访 Reel / 启航宣传片，11 个） | ✅ 依成片建立 + 视觉比对 + 测试；REFERENCE ONLY；来源 `projects/dfsc-2027/references/TEMPLATE_SOURCES.md` |
| 本地 Whisper CPU 真实转写 | ✅（57.9 s 音频 / 30.7 s，约 1.9× 实时） |
| Groq 转写 | ⏸ UNVERIFIED：无 `GROQ_API_KEY`（可选） |
| ChatCut 远程连接（只读） | ✅ PASS：Claude 网页 Custom Connector（`https://api.chatcut.io/api/external-mcp/mcp`，OAuth 由 Claude 网页管理）由 Cloud 宿主注入；发现 62 个工具，OAuth 调用成功，`list_projects` 返回 0 项目；无自定义 header 也可调用。不是本机插件，不需要桌面。旧结论（白名单 / 需桌面）作废 |
| ChatCut 剪辑 / 导入 / 生成 / 导出 | ⏸ UNVERIFIED：未测（须有具体 brief + 指定素材；不擅自创建项目或耗积分） |
| 根目录 CLAUDE.md（持久规则） | ✅ 已建立（在本分支；合并到 main 前只对选此分支的会话生效） |
| 金句卡引号重叠 | ✅ 已修复 + 回归测试 |
| 全新环境交接测试 | 见 SETUP_AUDIT §3 |
| 正式影片 | ⏸ 未开始：须有用户的具体剪辑 brief 与指定素材；不自行选人、发布或付费 |

## 5. 下一步（需要人决定）

1. 提供圆梦口号与活动资讯后，填入模板参数 `slogan` / `invite`（目前为占位）。
2. 如需 APPROVED：Reviewer 逐项查看 `templates/dfsc_*/preview.gif`（目前为 REFERENCE ONLY）。
3. 正式影片交付（链接已在首条 MASTER SETUP PROMPT 提供，无需重发）：
   - 小文件（QC 报告、字幕、交接文件）：在会话中请 Claude 用官方 Google Drive 连接器上传到 `config/drive_output.yaml` 的目录（已验证）。
   - 影片（无人值守）：按 `docs/zh/04_Drive_OAuth_自动上传.md` 完成一次浏览器授权，把 `STUDIO_DRIVE_OAUTH_CLIENT_ID / _CLIENT_SECRET / _REFRESH_TOKEN` 放进环境 secret，开新会话后：
     `studio drive auth` → `studio drive bigtest --folder 1a2f5BEUMFZS0TFQ1L1RvKbjoNty6mB__`（26 MB 真实上传、断点续传、下载、MD5、解码）→ `studio queue run --upload`。
     当前进度：用户已接受 Google Cloud 条款，正在 Create project / OAuth client 表单，停在最终创建前（由用户操作）。
4. 第一支正式影片：用户提供具体剪辑 brief（目的、长度、版式、受访者 / 素材文件、交付位置）后开始。
5. Admin：审核并合并 draft PR 到 `main`（或维持手动选分支）。团队共用账号，成员权限不需配置。

## 6. 给 Claude 的续接指令（贴到新会话）

> 继续 DFSC Cloud Video Studio。仓库 yukikimchi2-dfcc/DFSC-cloud-video-production-studio，分支 claude/cloud-ai-video-studio-setup-utp2z3。先读 CLAUDE.md、CONTINUE_SETUP.md 与 SETUP_AUDIT.md，执行第 3b 节指令并回报实际日志；没有具体剪辑 brief 和指定素材不制作正式影片、不要覆盖旧素材、不要开付费 GPU、不要建立密钥或排程任务；未实测的项目标 BLOCKED / UNVERIFIED；链接已在首条 MASTER SETUP PROMPT 提供，不要要求重发；ChatGPT 端的 Drive 上传成功不等于 Claude pipeline 可上传；ChatCut 只读连接已 PASS，但剪辑 / 导入 / 生成 / 导出未测，新 ChatCut 项目须有明确素材与 brief。
