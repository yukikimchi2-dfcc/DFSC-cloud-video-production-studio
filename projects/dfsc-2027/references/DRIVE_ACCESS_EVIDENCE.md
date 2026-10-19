# Google Drive 访问验收证据 · dfsc-2027

> 链接来源：第一条 MASTER SETUP PROMPT V2.0（已提供全部链接，无需重发）。
> 原则：**文件夹权限** 与 **Claude 运行环境的认证** 是两件不同的事，分开记录。

## 1. 文件夹权限（用户于 ChatGPT 端 Google Drive 连接器实测，2026-10-19）

| 文件夹 ID | 名称 | permissions |
|---|---|---|
| `1oBLTdKEbSDsTX1ozQten90vS0M3rkMdo` | DFCC_9Oct_JoshuaChin_SmartRental | 含 `{type: anyone, role: writer}` |
| `1x4YaQ1NOiW04Wnb_kM-N8N-1uT1sykG8` | DFCC_9Oct_YYLim_QJoyBalloon | 含 `{type: anyone, role: writer}` |
| `1kTg7UlLSuAaACuja_tVFHJ-uF571bYJ2` | DFCC_9Oct_ChiliAng_Eggteen_final(1) | 含 `{type: anyone, role: writer}` |

结论：**文件夹可写，权限不是阻碍。**（任何已登录的 Google 身份都可在其中新增文件。）

## 2. 跨端上传回读（ChatGPT 端连接器，用户提供）

- 上传至文件夹 `1oBLTdKEbSDsTX1ozQten90vS0M3rkMdo`：`STUDIO_SETUP_WRITE_TEST_20261019.txt`
- file ID `1IxNFMiIqOjUCycT_hv54nZAZ1eFnn5Sp` · https://drive.google.com/file/d/1IxNFMiIqOjUCycT_hv54nZAZ1eFnn5Sp/view
- 上传与回读均在 **ChatGPT 端** 完成。**这不是 Claude 云端 pipeline 的上传证据。**

## 3. Claude 云端运行环境独立验证（2026-10-19 10:00 UTC，容器 09:59:47 启动）

| # | 检查 | 结果 |
|---|---|---|
| 1 | 公开列出文件夹 1（gdown，无凭证） | ✅ 列出 `DFCC_9Oct_JoshuaChin_SmartRental.mov` 与 `STUDIO_SETUP_WRITE_TEST_20261019.txt` |
| 2 | 公开下载 `1IxNFMiI…`（Claude 端回读 ChatGPT 端上传的文件） | ✅ 198 bytes，MD5 `68a8b6deb2c922e3e8febda079ef3e13`，内容「Cloud Video Production Studio - setup connectivity test …」 |
| 3 | Claude 端**匿名写入**（Drive API multipart create 到文件夹 1） | ❌ **HTTP 401** `Login Required — Expected OAuth 2 access token` |
| 4 | `studio drive check --folder 1oBL…` | ❌ 无 Google 身份，干净退出（exit 2） |
| 5 | 环境变量 `CLOUDSDK_AUTH_ACCESS_TOKEN` | 存在但只是 14 字符占位值；Google tokeninfo 回 `invalid_token`，Drive API 401 → **不是可用凭证** |
| 6 | `gcloud auth list` / ADC 文件 / `secrets/` | 无登录账号 / 不存在 / 不存在 |
| 7 | Claude 连接器 `Google Drive`（官方） | 已安装但 `connect_incomplete`，`enabledInChat: false` |
| 8 | Claude 连接器 `drive`（自订，URL https://drive.google.com） | `needs_reconnect`，`enabledInChat: false`（显示 Connection issue） |

验收：
- **3a 公开读取（Claude 端）：✅ PASS**
- **3c 跨端文件可于 Claude 端读回：✅ PASS**
- **3b Claude 运行环境写入：⛔ BLOCKED — 原因是 Claude 端缺少 Google 认证，不是文件夹权限。** Google 不接受匿名写入，即使文件夹为 anyone:writer。

## 4. 官方 Google Drive 连接器实测（2026-10-19 10:09–10:11 UTC，用户完成授权后）

连接器状态：`Google Drive` → `installState: connected`、`connected: true`、`enabledInChat: true`（本会话可直接调用）；自订 `drive` 连接器仍 `needs_reconnect`（未使用）。授权账号：`yukikimchi2@gmail.com`。

| # | 操作（连接器工具） | 结果 |
|---|---|---|
| 1 | `get_file_permissions` / `get_file_metadata` 文件夹 1 `1oBL…` | ❌ `Requested entity was not found` |
| 2 | `get_file_metadata` 跨端测试文件 `1IxNFMiI…`、原有影片 `1kX4-TvO…` | ❌ not found |
| 3 | `search_files`：`parentId = 1oBL…` / `owner = 'me'` / `sharedWithMe = true` / `title contains 'DFCC'`；`list_recent_files` | 全部空 |
| 4 | `create_file` 到文件夹 1：`CLAUDE_CONNECTOR_SETUP_TEST_20261019T100948Z.txt` | ❌ `Requested entity was not found`（父文件夹不可见 → **未写入**） |
| 5 | 诊断：`create_file` 到该账号自己的 My Drive 根目录：`CLAUDE_CONNECTOR_DIAGNOSTIC_20261019T100948Z.txt` | ✅ id `1u8WdrXfTk5l4xG0e44AfapwC1Rn8TvMp`，362 bytes，owner yukikimchi2@gmail.com |
| 6 | `download_file_content` 读回 #5 | ✅ MD5 `a980068f0f7f8948adf7421fdeb3f51b`，与本地**逐字节相同** |
| 7 | 再次 `search_files owner = 'me'` | 只出现 #5 这一个文件 |

判读：
- **连接器认证与上传/读回能力：✅ PASS**（#5–#6）。
- **连接器写入原有文件夹 1：⛔ BLOCKED** —— 该连接器身份看不到任何既有文件（包括 anyone:writer 的三个文件夹），只看得到自己建立的文件。最可能是连接器授权的是**受限范围（只限本应用建立/打开的文件）**；或授权账号与能看到这些文件夹的账号不同。文件夹权限本身不是原因。
- 诊断文件 `1u8Wdr…` 留在 yukikimchi2@gmail.com 的 My Drive 根目录，可自行保留或删除（未自动删除）。

### 4.1 下一步（择一，由你决定）
1. 由文件夹拥有者把文件夹 1 **直接共享**给 `yukikimchi2@gmail.com`（Editor）后重测：若连接器授权是完整范围，文件夹会出现在「与我共享」并可写入；若仍 not found，即确认是受限范围。
2. 若连接器只能操作自己建立的文件：改由连接器在 yukikimchi2@gmail.com 的 Drive 建立专用交付文件夹（例如 `Cloud Video Production Studio/06_Project_Previews`），再共享给团队；之后对话内上传都放在那里。（需你同意后才建立。）

## 4.2 专用工作室输出目录（2026-10-19 10:13–10:19 UTC，连接器建立）

- 先搜索连接器可见范围：无 `Cloud Video Production Studio` 或类似目录 → 在 yukikimchi2@gmail.com 下新建。
- 建立 **37 个目录**（根 + 10 个一级 + 23 个二级 + 05/06/08 下的 `dfsc-2027`），全部 `canAddChildren: true`；ID 清单：`config/drive_output.yaml`。
- 根目录：https://drive.google.com/drive/folders/1Lk3HhFLwgQi30d-2lRDFvqn7gRckszmU（仅拥有者可见，尚未共享给团队）
- **没有复制或移动任何原素材**；原有三个 DFCC 文件夹保持为只读参考来源（容器以公开链接读取）。

上传 + 读回 + 校验（连接器 `create_file` → `download_file_content` → 容器内 MD5 / ffprobe）：

| 文件 | 位置 | 大小 | MD5 本地 = 读回 | 其他 |
|---|---|---|---|---|
| `CLAUDE_CONNECTOR_SETUP_TEST_20261019T100948Z.txt` | 06_Project_Previews/dfsc-2027 | 362 B | `a980068f…` ✅ | |
| `setup_check_v001_final_qc.md`（真实 QC 报告） | 08_QC_Reports/dfsc-2027 | 1485 B | `feb263ed…` ✅ | |
| `TEST_binary_roundtrip_20261019T101541Z.png` | 06_Project_Previews/dfsc-2027 | 79 B | `71ad0444…` ✅ | PNG 可解码 |
| `TEST_tiny_16x16_1frame_20261019T1019Z.mp4` | 06_Project_Previews/dfsc-2027 | 825 B | `e175b04c…` ✅ 逐字节相同 | ffprobe：h264 High 16×16、1 帧、0.1 s；完整解码 OK |
| （失败）`TEST_binary_roundtrip…mp4` 4.9 KB | — | — | — | ❌ 连接器回「not a valid base64 string」：6564 字符 base64 经模型逐字转录出错，未上传 |

### 4.3 连接器的限制（实测 + 工具定义）

- `create_file` 只接受**内嵌内容**：`textContent`（UTF-8）或 `base64Content`；**没有**本地文件路径、URL、容器文件引用参数 → 连接器**读不到云端容器里的渲染文件**。
- 工具定义**未标示大小上限** → 最大可接受体积 **UNVERIFIED**；实际上内容必须由模型逐字输出，KB 级已出现转录错误。
- `download_file_content` 回传 base64，同样经过模型上下文。
- 连接器只看得到自己建立的文件（看不到原有 DFCC 文件夹）。

### 4.4 验收结论

| 项目 | 结论 |
|---|---|
| 连接器：建立目录 / 子目录 | ✅ PASS |
| 连接器：上传 + 读回 文本 / Markdown 报告 | ✅ PASS |
| 连接器：极小二进制（79 B PNG、825 B MP4）完整往返 | ✅ PASS |
| **连接器：正式体积 MP4 交付（Preview ≤30 MB / Final）** | ❌ **NOT PASS** —— 只能内嵌 base64、不能引用容器文件；不可作为生产交付方案 |
| 无人值守 `studio queue run --upload` | ⛔ BLOCKED（下节） |

可用的人工参与流程：对话中由 Claude 用连接器建立目录、上传 QC 报告 / 交接文件 / 字幕等小文件。**正式影片**需走无人值守上传（补容器身份），或由人从云端工作区下载后手动上传。

## 5. 无人值守上传（`studio queue run --upload` / `studio drive check`）—— 与连接器分开验收

| 检查 | 结果 |
|---|---|
| 容器内 Google 身份 | 无（`STUDIO_DRIVE_TOKEN` / `STUDIO_DRIVE_CREDENTIALS` 未设；`CLOUDSDK_AUTH_ACCESS_TOKEN` 为 14 字符无效占位值）。连接器的 OAuth **不会**出现在容器里，也未尝试提取浏览器 token |
| `studio drive check --folder 1oBL…` | ⛔ exit 2：no Google identity |
| `studio queue run --upload` 上传器 | 预览目标已设定：`drive.previews_folder_id = 1a2f5BEUMFZS0TFQ1L1RvKbjoNty6mB__`（06_Project_Previews/dfsc-2027）；仍因无 Google 身份而 BLOCKED |

结论：**无人值守上传 BLOCKED**，只差容器可用的 Google 身份（见下节）。该身份需对输出目录有写入权限（输出目录由 yukikimchi2@gmail.com 拥有：用该账号的 OAuth token，或把输出目录共享给服务账号）。

## 6. 让 Claude 端可写的具体做法（择一；未代为执行，未建立任何密钥）

**A. Claude 对话/会话内写入（使用连接器，不经 pipeline 代码）**
1. 打开 https://claude.ai/customize/connectors
2. 「Google Drive」显示 *connect_incomplete* → 点 Connect，用一个 Google 帐号完成授权（同意上传 / 读取范围）。
3. 自订「drive」连接器（URL `https://drive.google.com` 不是 MCP 服务器地址）显示 *needs_reconnect* → 建议移除或停用，避免混淆。
4. 开一个**新会话**（连接器在会话启动时载入），并确认该会话中 Google Drive 连接器为启用状态。
5. 验收：由 Claude 用连接器上传一个新测试文件到文件夹 1 并读回。

**B. 自动 pipeline 写入（`studio queue run --upload`、`studio drive setup`）**
需要在云端环境设定（环境选单 → Edit → 环境变量 / Network secrets）提供一个 Google 身份，二选一：
- `STUDIO_DRIVE_TOKEN`：某位团队成员 Google 帐号的 OAuth 授权文件路径，或
- `STUDIO_DRIVE_CREDENTIALS_JSON`：服务账号 JSON（由 Admin 自行决定是否建立）。

因三个文件夹已是 anyone:writer，**不需要再额外共享**给该身份。之后执行：
```bash
studio drive check --folder 1oBLTdKEbSDsTX1ozQten90vS0M3rkMdo   # 3b：上传新测试文件 → 回读 → MD5 比对（不删除、不覆盖）
```
