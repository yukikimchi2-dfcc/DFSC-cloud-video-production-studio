# Motion Graphics Templates

每个模板一个文件夹：`template.yaml`（元数据 + 可调参数）、`preview.png`（中段静帧）、
`preview.gif`（动画预览）、`test_record.json`（最近一次自动测试记录）。

- 代码：`studio/motion/templates.py`（`@register("<id>")` 的 builder）
- 列出模板：`python -c "from studio.motion.templates import list_templates; print([t['id'] for t in list_templates()])"`
- 重新生成全部预览：`python tools/demo_motion.py --previews`
- 使用：`build_template("<id>", {参数}, brand)` 返回 Layer 列表，加入任意 Timeline。

`review_status`：APPROVED / REFERENCE ONLY / REJECTED / UNREVIEWED。只有 APPROVED 可作为品牌标准。
新增模板：建文件夹 + template.yaml，在 templates.py 写 builder，跑 `pytest tests/test_motion_templates.py`。

## DFSC 两套模板（依既有成片建立 · REFERENCE ONLY）

来源、时间码与测量值：[`projects/dfsc-2027/references/TEMPLATE_SOURCES.md`](../projects/dfsc-2027/references/TEMPLATE_SOURCES.md)。
用户授权以成片为风格基准（2026-10-19），**非逐项审美批准**。只能搭配 `dfsc-2027` 品牌（`requires_project`）。
无来源文案（圆梦口号、活动资讯、人名）一律为 `〔…〕` 占位参数。

| 家族 | 模板 |
|---|---|
| 采访 Reel（繁中字幕、绿色关键词、云朵片尾） | `dfsc_interview_top_label`、`dfsc_interview_big_title`、`dfsc_interview_name_tag`、`dfsc_interview_subtitle`、`dfsc_interview_reel`（完整结构） |
| 启航宣传片（海军蓝网格、北极星） | `dfsc_launch_background`、`dfsc_launch_title`、`dfsc_launch_alumni_orbit`、`dfsc_launch_stats`、`dfsc_launch_sequence`（完整结构） |
| 共用 | `dfsc_end_card` |

测试：`pytest tests/test_motion_dfsc_templates.py`。
