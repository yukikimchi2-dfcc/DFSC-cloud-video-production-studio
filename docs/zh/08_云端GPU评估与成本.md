# 云端 GPU 评估与成本估算

> **状态：仅评估，未开通任何付费资源。** 开通前需要你书面批准（预算、平台、上限）。

## 1. 现在需要 GPU 吗？

| 工作 | CPU（目前环境：4 核 / 16 GB） | GPU 的好处 |
|---|---|---|
| Motion Graphics / 合成渲染（本系统的 NumPy+OpenCV 引擎） | 可以，CPU 计算为主 | 很小 —— 引擎目前不使用 CUDA |
| H.264 编码 | 可以（libx264 质量最好） | NVENC 更快但同码率画质较差，CRF 16 正式输出建议仍用 libx264 |
| Whisper large-v3-turbo 转写 | 可以但慢（约 1–3× 实时） | **明显**（约 20× 实时以上） |
| 人脸追踪（Haar） | 可以 | 无 |

**建议**：先全部用 CPU（免费、零维护）。等开始处理大量采访素材时，只把 **Whisper 转写** 放到按需 GPU。

## 2. 平台比较（价格来自第三方汇总网站，2026-10 查询，开通前须以官方页面为准）

| 平台 | 机型 | 约略单价 | 特点 |
|---|---|---|---|
| RunPod Community Cloud | RTX 4090 24GB | ≈ US$0.34 /小时 | 最便宜；个人主机提供，可靠性较低 |
| RunPod Secure Cloud | RTX 4090 / L4 | ≈ US$0.59–0.89 / ≈ US$0.39–0.49 /小时 | 数据中心；价格各来源不一致 |
| RunPod Serverless | 4090 worker | ≈ US$1.10 /小时（按秒计费） | 不用时 0 费用、自动缩放；最适合「偶尔转写」 |
| Google Cloud g2-standard-4 | 1× L4 | ≈ US$0.71 /小时 on-demand；≈ US$0.40 spot | 与 Google Drive 同生态、帐单/权限统一；spot 可能被回收 |

## 3. 成本估算

指令：`studio gpu estimate --seconds 60 --renders 3 --transcribe-minutes 30 --hourly-usd 0.40`

假设一支 60 秒广告：30 分钟采访素材转写 + 3 次渲染，加上 15 分钟自动停止前的闲置：

| 方案 | 估算 |
|---|---|
| 全部 CPU（现况） | US$0 额外费用 |
| GCP L4 spot（$0.40/h） | 约 US$0.15 / 支 |
| RunPod 4090 community（$0.34/h） | 约 US$0.13 / 支 |
| 每月 20 支影片 | 约 US$3–5 / 月（只用于转写） |

真正的成本风险是**忘记关机**：L4 on-demand 24 小时不关 ≈ US$17 / 天。

## 4. 成本控制（已写入代码）

`studio/gpu/guard.py`：除非同时满足以下条件，系统**拒绝**启动付费 GPU：
1. `config/defaults.yaml` 的 `gpu.provider` 不是 `none`（目前是 `none`）
2. 环境变量 `STUDIO_GPU_APPROVAL` 写明批准人 / 日期 / 预算
3. 单价不超过 `gpu.max_hourly_usd`（目前 US$1.00）

每次判断（允许或拒绝）都记录在 `workspace/gpu_decisions.jsonl`。其他保护：`auto_stop_minutes: 15` 自动停止、渲染队列失败重试上限 3 次、每次渲染记录耗时。

## 5. 建议的下一步（需要你决定）

- **方案 A（推荐）**：继续 CPU；需要大量转写时开 **RunPod Serverless**（按秒计费、不用不收费）。
- **方案 B**：若希望帐单与 Google Drive 统一，使用 **GCP L4 spot** + 15 分钟自动关机。

两者都需要：(1) 你批准预算上限；(2) 提供 API 金钥（`RUNPOD_API_KEY` 或 GCP 服务账号），放在环境密钥中。

## 资料来源
- https://northflank.com/blog/runpod-gpu-pricing
- https://www.hivenet.com/post/runpod-pricing-complete-guide-to-gpu-cloud-costs
- https://www.synpixcloud.com/blog/rtx-4090-cloud-rental-worth-it
- https://computeprices.com/providers/google/gpus/l4
- https://www.thundercompute.com/blog/google-cloud-gpu-instances
- https://www.economize.cloud/resources/gcp/pricing/compute-engine/g2-standard-4/
