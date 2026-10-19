# 云端 GPU 评估：免费优先方案

> **政策：免费优先。** 系统默认不使用任何付费资源；付费 GPU 仍保留守门机制（须书面批准），但不在推荐方案内。

## 1. 先看清楚：哪里真的需要 GPU？

| 工作 | 需要 GPU？ | 免费做法 |
|---|---|---|
| Motion Graphics / 合成渲染 | **不需要**（引擎是 NumPy + OpenCV，CPU 计算） | 云端开发环境的 CPU |
| H.264 编码（CRF 16 正式输出） | 不需要（libx264 画质最好，本来就是 CPU） | CPU |
| 人脸追踪、风格分析、QC | 不需要 | CPU |
| **Whisper large-v3-turbo 转写** | 唯一受益于 GPU 的环节 | ① Groq 免费 API ② 本地 CPU ③ Kaggle 免费 GPU |

结论：**只有转写需要考虑 GPU，而转写有完全免费的做法。**

## 2. 推荐方案（三层，全部免费）

### 方案 ① Groq 免费 Whisper API —— 主要方案（已接入代码）
- 跑的是同一个 `whisper-large-v3-turbo` 模型，由 Groq 托管；我们这边不需要 GPU。
- 免费额度（第三方整理，以 Groq 控制台为准）：每分钟 20 次请求、每天 2,000 次请求，**每天约 8 小时音频**（28,800 秒），单个文件 25 MB。
- 系统处理方式：音频自动转为 16 kHz Opus，按约 10 分钟、在静音处切段（每段远小于 25 MB），遇到限流（429）自动等待重试，时间码自动接回原片。
- 设定：在环境密钥加入 `GROQ_API_KEY`（免费注册 https://console.groq.com/keys），`config/defaults.yaml` 的 `transcription.backend: auto` 有金钥时就自动使用 Groq。
- 需要允许网域：`api.groq.com`。
- 注意：音频会上传到 Groq 处理。若某些采访内容不可外传，对该项目设定 `transcription.backend: local`。

### 方案 ② 本地 CPU 转写 —— 备用 / 机密素材
- faster-whisper（int8）在现有 4 核 CPU 上运行，速度约为实时的 1–3 倍（新会话下载模型后会实测并更新此处）。
- 完全免费、音频不离开环境；适合少量或机密素材。
- 需要允许网域：`huggingface.co`、`*.hf.co`（首次下载模型权重）。

### 方案 ③ Kaggle Notebooks 免费 GPU —— 大批量时
- 免费额度约每周 30 小时 GPU（P100 或 2×T4），单次最长 12 小时。
- 适合一次转写大量采访（例如数十小时素材）；可用 Kaggle API 推送 notebook 并取回结果。
- 需要：Kaggle 帐号 API Token（`KAGGLE_API_TOKEN`）、允许 `www.kaggle.com`。等真的有大批量需求时再接上。

### 其他免费选项（评估过，不推荐为主力）
| 选项 | 原因 |
|---|---|
| Google Colab 免费版 | 额度不固定、需要浏览器互动，无法自动化 |
| Lightning AI 免费额度（约每月 15 credits） | 额度小、月底失效 |
| Modal（约每月 US$30 免费额度） | 需要绑卡，超额会自动扣款，违反「免付费」原则 |
| Google Cloud US$300 试用金 | 试用帐号通常要升级为付费帐号才能用 GPU；90 天后失效 |
| Hugging Face ZeroGPU | 共享资源、额度有限，适合 demo 而非生产 |

## 3. 成本

| 项目 | 费用 |
|---|---|
| 渲染、Motion Graphics、QC、风格分析（CPU） | US$0 |
| 转写：Groq 免费层（每天约 8 小时音频以内） | US$0 |
| 转写：本地 CPU | US$0 |
| 大批量转写：Kaggle（每周约 30 小时 GPU 以内） | US$0 |

一支 60 秒广告通常只需转写 10–60 分钟采访素材，远低于每日免费额度。

## 4. 成本保护（代码）

- `config/defaults.yaml` → `gpu.provider: none`；付费平台（runpod / gcp）必须同时有 `STUDIO_GPU_APPROVAL` 才能启动（`studio/gpu/guard.py`），每次判断记录在 `workspace/gpu_decisions.jsonl`。
- 本仓库**不包含**任何会自动开通付费资源的代码。

## 资料来源（第三方整理，开通前以官方页面为准）
- Groq 免费层：https://www.free-model.com/models/groq/whisper-large-v3-turbo/ ，https://spokenly.app/blog/free-speech-to-text-apis ，https://www.eesel.ai/blog/groq-pricing
- Kaggle：https://agentdeals.dev/vendor/kaggle
- 免费 GPU 比较：https://www.spheron.network/blog/free-gpu-cloud-credits-2026/ ，https://aimultiple.com/free-cloud-gpu ，https://www.spheron.network/blog/google-colab-alternatives-8-gpu-clouds-compared-2026/
- GCP 试用：https://www.gmicloud.ai/blog/where-can-i-get-free-gpu-cloud-trials-in-2026-a-complete-guide
