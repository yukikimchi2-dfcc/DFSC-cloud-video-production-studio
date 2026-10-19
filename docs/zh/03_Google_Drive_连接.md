# Google Drive 连接与素材系统

Google Drive 是团队的素材平台；GitHub 只放代码与配置，**不放影片**。

## 1. 现状（2026-10-19 实测）

Drive 分成两种能力，**分开验收**：

| 能力 | 需要什么 | 状态 |
|---|---|---|
| **公开读取**：「知道链接的任何人可查看」的文件夹 | 只需网络放行 `drive.google.com`、`drive.usercontent.google.com`，**不需要 OAuth / 服务账号** | ✅ 已验证：3 个参考文件夹列出 + 下载 + 完整解码（Test 3a） |
| **持久化写入**：建立文件夹结构、上传 Preview / 成品 / QC 报告、读取私人文件夹 | 服务账号金钥或可用的 Drive 连接器 | ⛔ BLOCKED（未提供凭证；自订 drive connector 显示 Connection issue，不能使用） |

公开读取的做法：
```bash
studio references ingest dfsc-2027          # 读取 project.yaml 里 drive.reference_folders 的公开链接
python3 -m pytest -q tests/test_setup_acceptance.py -k 3a
```
公开读取不提供 MD5，系统改以 ffprobe 完整解码确认文件完整。

## 2. 写入授权步骤（由 Admin 执行一次，需要时）

推荐使用 **Service Account（服务账号）**：不依赖任何人的个人 Google 账号，人员离职也不影响系统。

1. 打开 Google Cloud Console → 建立（或选用）一个项目 → 启用 **Google Drive API**。
2. IAM → Service Accounts → 建立服务账号，例如 `video-studio@<项目>.iam.gserviceaccount.com`。
3. 为该账号建立 **JSON 金钥**并下载。**不要**提交到 GitHub、不要贴在聊天里。
4. 在 Google Drive 中，把下列文件夹 **共享给服务账号的 e-mail（编辑者权限）**：
   - 三个参考文件夹（client 提供的链接）
   - 将要放置 `Cloud Video Production Studio/` 的上层文件夹（建议用 Shared Drive）
5. 把 JSON 内容放进云端环境的密钥：
   - Claude Code 云端：环境设定 → Environment variables，新增 `STUDIO_DRIVE_CREDENTIALS_JSON`（JSON 全文），
     然后在会话中执行 `bash .devcontainer/write-secrets.sh`
   - GitHub Codespaces：Repository → Settings → Secrets → Codespaces，新增同名密钥（devcontainer 会自动写入）

> 服务账号只能看到**被共享给它**的文件夹，看不到任何人的其他文件。

## 3. 验证（Test 3）

```bash
source secrets/env.sh
studio drive check --folder <测试文件夹ID>
```
会实际执行：列出文件（读）→ 上传一个 `studio_access_check_*.txt`（写）→ 下载回来并比对 MD5（完整性）。
测试文件**不会被删除**（系统政策：不删除任何 Drive 文件），可自行归档。

## 4. 建立 / 整合文件夹结构

```bash
studio drive setup --parent <上层文件夹ID>
```
- 逐层「先找再建」：已存在的同名文件夹**直接沿用**，不会重复建立，也不会移动原有文件。
- 输出每个文件夹是 `exists`（沿用）还是 `created`（新建）及其 ID。
- 可重复执行，第二次执行应全部为 `exists`。

结构（见 `studio/storage/base.py: STUDIO_STRUCTURE`）：
```
Cloud Video Production Studio/
├── 01_Brand_Library/  (Brand_Guidelines, Logos, Fonts, Color_Palettes, Brand_Assets)
├── 02_Source_Materials/  (Raw_Videos, Interviews, Photos, Product_Images, Audio, Music)
├── 03_Style_References/  (Previous_Edits, Approved_Videos, Motion_References, Editing_References, Visual_References)
├── 04_Motion_Graphics_Library/  (Typography, Title_Cards, Transitions, Stickers, Particles, Lower_Thirds, Outro_Templates)
├── 05_Active_Projects/
├── 06_Project_Previews/
├── 07_Approved_Final_Videos/
├── 08_QC_Reports/
├── 09_Archive/
└── 10_Team_Documentation/
```

## 5. 素材索引（不复制旧素材）

```bash
studio drive scan --folder <文件夹ID> --label "参考A" --brand dfsc-2027 --batch 500
```
- 只读取**元数据**，不下载文件；写入 `workspace/asset_index.jsonl`。
- 每笔记录：来源、文件 ID、路径、版本、MD5、大小、修改时间、类型，以及团队可编辑的
  `purpose`（用途）、`brand`（品牌归属）、`review_status`、`notes`、`project`。
- `--batch` 限制每次新增/变更的笔数，大型 Drive 分多次扫描。
- 再次扫描时自动识别新增 / 变更（保留旧版本记录），团队的标注不会被覆盖。
- 新素材默认 `review_status = UNREVIEWED` —— **存在于 Drive 不代表是认可的作品**。

## 6. 渲染时的下载 / 上传

- 渲染需要的素材下载到云端临时工作区 `workspace/`（git-ignored），使用 HTTP Range **断点续传**，完成后比对 MD5，失败的文件改名为 `.corrupt` 不会被使用。
- 上传使用 Drive resumable upload，完成后比对 MD5。
- 同名文件上传会成为新文件，不覆盖旧文件。
- `studio queue run --upload` 会把成品上传到项目的 `drive.previews_folder_id`。
