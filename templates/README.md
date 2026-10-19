# Motion Graphics Templates

每个模板一个文件夹：`template.yaml`（元数据 + 可调参数）、`preview.png`（中段静帧）、
`preview.gif`（动画预览）、`test_record.json`（最近一次自动测试记录）。

- 代码：`studio/motion/templates.py`（`@register("<id>")` 的 builder）
- 列出模板：`python -c "from studio.motion.templates import list_templates; print([t['id'] for t in list_templates()])"`
- 重新生成全部预览：`python tools/demo_motion.py --previews`
- 使用：`build_template("<id>", {参数}, brand)` 返回 Layer 列表，加入任意 Timeline。

`review_status`：APPROVED / REFERENCE ONLY / REJECTED / UNREVIEWED。只有 APPROVED 可作为品牌标准。
新增模板：建文件夹 + template.yaml，在 templates.py 写 builder，跑 `pytest tests/test_motion_templates.py`。
