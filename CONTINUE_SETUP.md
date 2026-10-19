# 续接 Setup（给下一个会话 / 下一位成员）

> 最后更新：2026-10-19 · 阶段：**Setup（未完成）· 不制作正式影片**
> 完整审计与验收矩阵：[SETUP_AUDIT.md](SETUP_AUDIT.md)

## 1. 位置

| 项目 | 值 |
|---|---|
| 仓库 | https://github.com/yukikimchi2-dfcc/DFSC-cloud-video-production-studio |
| 分支 | `claude/cloud-ai-video-studio-setup-utp2z3`（沿用此分支，未开 PR） |
| 云端环境 | Default（`env_01YZBZzYR4G41RjEdnZeQepN`），Network access = Limited + Allowed domains |
| 项目 | `projects/dfsc-2027/`（第十一屆 圓夢工場。創業大賽 2027 — 啟航 北極星） |

## 2. 参考链接

| 类型 | 链接 | 读取方式 | 状态 |
|---|---|---|---|
| Drive 素材 1 | https://drive.google.com/drive/folders/1oBLTdKEbSDsTX1ozQten90vS0M3rkMdo | 公开链接（gdown） | ✅ 已读取 |
| Drive 素材 2 | https://drive.google.com/drive/folders/1x4YaQ1NOiW04Wnb_kM-N8N-1uT1sykG8 | 公开链接 | ✅ |
| Drive 素材 3 | https://drive.google.com/drive/folders/1kTg7UlLSuAaACuja_tVFHJ-uF571bYJ2 | 公开链接 | ✅ |
| Notion | https://app.notion.com/p/Dreamfactory-3f14ddbea63a8022a1f1e3d4c4d1b038 | `app.notion.com` 被挡 → 用同一页面 ID 走 `www.notion.so` | ✅ 已导出 `projects/dfsc-2027/references/notion/` |
| Facebook 1 | https://www.facebook.com/share/r/1CL7DzWC9D/ | yt-dlp | ✅ |
| Facebook 2 | https://www.facebook.com/share/v/1DSeQULbZm/ | yt-dlp | ✅ |

## 3. 新会话开工（复制执行）

云端容器是临时的：`workspace/`（下载的参考影片、Whisper 模型、渲染）**不会保留**，需要时重新取得。

```bash
cd /home/user/DFSC-cloud-video-production-studio        # 或 git clone 上面的仓库 + 分支
git checkout claude/cloud-ai-video-studio-setup-utp2z3 && git pull
pip install -r requirements.txt && pip install -e .      # SessionStart hook 通常已自动完成
studio audit                                             # 确认网络：drive / huggingface / facebook / notion.so 应为 reachable
python3 -m pytest -q -m "not network"                    # 基线测试
studio models fetch                                      # 本地 Whisper（1.6 GB，约 4 分钟；HF 可能先限流 3 分钟）
studio references ingest dfsc-2027                       # 重新下载参考影片到 workspace（报告已在 git，不会覆盖已审核档案）
python3 -m pytest -q                                     # 含 network 测试（Drive 公开读取、真实转写）
python3 tools/notion_public.py "https://app.notion.com/p/Dreamfactory-3f14ddbea63a8022a1f1e3d4c4d1b038" \
        projects/dfsc-2027/references/notion/dreamfactory.md --subpages   # Notion 有更新时
```

## 4. 任务状态

| 任务 | 状态 |
|---|---|
| 环境审计、代码系统、渲染、QC、团队流程、中文文档 | ✅ 完成 |
| Drive **公开读取**（3 个文件夹，原公开链接） | ✅ 验收通过 |
| Drive **持久化写入**（上传成品 / 建立文件夹结构） | ⛔ BLOCKED：无 OAuth / 服务账号；用户指示不建立密钥 |
| Facebook / Notion 参考导入 | ✅ |
| 风格分析（5 支）+ 草稿档案 | ✅ 完成 · ⏳ 待 Reviewer 审核（全部 UNREVIEWED） |
| 本地 Whisper CPU 真实转写 | ✅（57.9 s 音频 / 30.7 s，约 1.9× 实时） |
| Groq 转写 | ⏸ UNVERIFIED：无 `GROQ_API_KEY`（可选） |
| 金句卡引号重叠 | ✅ 已修复 + 回归测试 |
| 全新环境交接测试 | 见 SETUP_AUDIT §3 |
| 正式影片 | 🚫 未开始（等客户确认 Setup 完成） |

## 5. 下一步（需要人决定）

1. 回答 `projects/dfsc-2027/references/STYLE_FINDINGS.md` 第 7 节的 4 个问题（繁/简字幕、圆梦口号、绿色标签与云朵片尾是否固定、3 支采访是否为已审核版本）。
2. Reviewer 审核 `style_profiles/DFSC_Interview_Reel.yaml`、`templates/dfsc2027_north_star_open/preview.gif`。
3. 决定 Drive 写入方式（服务账号 / 可用的 Drive 连接器），之后跑 Test 3b：`studio drive check --folder <ID>`。
4. 客户确认 Setup 完成 → 才开始第一支正式影片。

## 6. 给 Claude 的续接指令（贴到新会话）

> 继续 DFSC Cloud Video Studio 的 Setup。仓库 yukikimchi2-dfcc/DFSC-cloud-video-production-studio，分支 claude/cloud-ai-video-studio-setup-utp2z3。先读 CONTINUE_SETUP.md 与 SETUP_AUDIT.md，执行第 3 节指令并回报实际日志；不要制作正式影片、不要覆盖旧素材、不要开付费 GPU、不要建立密钥或排程任务；未实测的项目标 BLOCKED / UNVERIFIED。
