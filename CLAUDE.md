# DFSC Cloud Video Production Studio — 持久规则

Claude Code 在本仓库开新会话时会自动读取本文件。细节与当前状态：
- [CONTINUE_SETUP.md](CONTINUE_SETUP.md) — 续接步骤、链接、任务状态、团队启动指令
- [SETUP_AUDIT.md](SETUP_AUDIT.md) — 验收矩阵与证据（PASS / NOT PASS / BLOCKED）
- [projects/dfsc-2027/HANDOVER.md](projects/dfsc-2027/HANDOVER.md) — 项目交接（`studio project handover dfsc-2027` 生成）

开工先读这三个文件，执行 `studio audit`，再回报实际结果。

## 规则

1. **正式剪辑**：要有用户给出的具体剪辑 brief 和指定素材才能开始。不要自行挑选受访者或素材，不要发布或公开分享，不要购买服务或开启付费 GPU（`studio/gpu/guard.py`）。
2. **原素材只读**：不覆盖、不修改、不移动、不删除原始素材，包括三个 DFCC 参考文件夹（`projects/dfsc-2027/project.yaml`）。渲染只产生新版本（`_v###`）。Drive 只新增文件。
3. **凭证**：不要在聊天、日志、Git 或文档中输出任何密钥、token、secret。凭证只放环境 secret（`STUDIO_DRIVE_OAUTH_*`）。不提取浏览器 token 或 cookie，不擅自创建密钥、不扩大权限、不添加协作者或共享。
4. **如实验收**：没有实测过的项目标 BLOCKED 或 UNVERIFIED。ChatGPT 端或连接器的成功不等于 Claude pipeline 已通过。测试素材一律合成，并标记「TEST · 合成測試素材」。
5. **风格**：DFSC 两套模板为 REFERENCE ONLY（以用户授权的既有成片为基准，不是逐项批准）。没有来源的文案（口号、活动资讯、人名）用参数，不编造。
6. **持久化**：云端容器是临时的。`workspace/` 和 `renders/` 不进 Git。成果要 commit 并 push 到工作分支；不改默认分支，不自行合并 PR。

## 常用命令

```bash
studio audit                       # 环境检查
python3 -m pytest -q -m "not network"
studio templates list
studio drive auth                  # 只显示凭证来源，不显示值
```
