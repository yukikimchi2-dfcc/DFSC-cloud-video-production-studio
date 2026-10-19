# Cloud AI Video Production Studio · DFSC

Dream Factory 的云端 AI 视频制作系统：以代码为核心的剪辑、Motion Graphics、AI 转写与选段、字幕、音频、质量检测、版本管理与团队交接。不依赖 CapCut / Premiere 或任何个人电脑。

> **目前阶段：Setup。** 在客户确认 Setup 完成前，不制作正式影片。所有测试影片均为合成素材，并标记为「TEST · 合成測試素材」。
> 当前状态与验收矩阵见 **[SETUP_AUDIT.md](SETUP_AUDIT.md)**；新会话 / 新成员续接见 **[CONTINUE_SETUP.md](CONTINUE_SETUP.md)**。

## 快速开始

```bash
pip install -r requirements.txt && pip install -e .     # 或使用 Dockerfile / Codespaces
studio audit                                            # 环境检查
pytest -q -m "not network"                              # 自动测试
studio render test-card --mode preview                  # 合成测试渲染 → renders/dfsc-2027/test_card_v001_preview.mp4
studio templates list                                   # Motion Graphics 模板
studio project list                                     # 项目与状态
studio models fetch                                     # 本地 Whisper 模型（免费 CPU 转写）
studio references ingest dfsc-2027                      # 参考资料导入 + 风格分析
```

## 文档（中文）

| 文档 | 内容 |
|---|---|
| [docs/zh/00_系统架构.md](docs/zh/00_系统架构.md) | 架构、代码结构、持久化原则 |
| [docs/zh/01_团队使用手册.md](docs/zh/01_团队使用手册.md) | 新项目、上传素材、模板、字幕、Motion Graphics、Preview、审核、版本、正式输出、交接 |
| [docs/zh/03_Google_Drive_连接.md](docs/zh/03_Google_Drive_连接.md) | Drive 授权、文件夹结构、素材索引 |
| [docs/zh/04_Drive_OAuth_自动上传.md](docs/zh/04_Drive_OAuth_自动上传.md) | 无人值守大文件上传：OAuth 配置清单、断点续传、验收 |
| [docs/zh/08_云端GPU评估与成本.md](docs/zh/08_云端GPU评估与成本.md) | GPU 平台比较与成本控制 |
| [templates/README.md](templates/README.md) | Motion Graphics 模板 |
| [style_profiles/README.md](style_profiles/README.md) | 风格档案审核流程 |

## 系统规则

1. 每次渲染产生新版本（`project_v001_preview.mp4` …），**永不覆盖**。
2. Google Drive 只新增，不删除、不移动；所有传输比对 MD5。
3. 风格分析结果一律 `UNREVIEWED`，人工批准后才成为品牌标准。
4. 付费 GPU 无书面批准一律拒绝（`studio/gpu/guard.py`）。
5. 云端容器是临时的：工作结束一定要 commit + push。
