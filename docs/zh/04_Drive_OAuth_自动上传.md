# Drive OAuth · 无人值守上传（`studio queue run --upload`）配置

> 状态（2026-10-19）：代码已就绪并以本地模拟端点验证；**真实 Google 上传 BLOCKED，等待一次浏览器授权**。
> 本文件只列配置，**不含任何密钥 / token**。所有值只放进云端环境的受控 secret，不进 Git、不贴聊天。

## 1. 为什么是这个方案（依据 Google 官方文档）

| 方案 | 结论 | 依据 |
|---|---|---|
| OOB 复制粘贴 code | ❌ 已弃用 | [OOB Migration Guide](https://developers.google.com/identity/protocols/oauth2/resources/oob-migration) |
| Device flow（电视 / 受限输入） | ❌ 只允许 `drive.file`、`drive.appdata`，碰不到现有目录 | [TV & Limited-Input Devices](https://developers.google.com/identity/protocols/oauth2/limited-input-device) |
| 服务账号 + 个人 Gmail | ❌ 服务账号没有存储配额、不能拥有文件；共享云端硬盘需 Workspace | [Shared drives overview](https://developers.google.com/workspace/drive/api/guides/about-shareddrives) |
| 浏览器 cookie / 提取连接器 token | ❌ 不使用 | — |
| **Desktop app + loopback（127.0.0.1）+ PKCE** | ✅ **推荐**：在你自己的电脑跑一次 `tools/drive_oauth_bootstrap.py` | [OAuth 2.0 for Desktop Apps](https://developers.google.com/identity/protocols/oauth2/native-app)、[Loopback migration](https://developers.google.com/identity/protocols/oauth2/resources/loopback-migration)（桌面端继续支持） |
| **自有 Web client + OAuth Playground 回调** | ✅ 备选：只用浏览器，不需本地 Python | [OAuth Playground（自有凭证）](https://developers.google.com/google-ads/api/docs/oauth/playground) |

**刷新令牌寿命**：External + 发布状态 *Testing* → refresh token **7 天后失效**；改为 *In production* 后一般不过期（被撤销或约 6 个月未使用除外）。Playground 若用其**默认** client，refresh token 约 24 小时失效 —— 必须用**自有** client。依据：[Manage App Audience](https://support.google.com/cloud/answer/15549945)、[OAuth app state overview](https://developers.google.com/identity/protocols/oauth2/production-readiness/overview)。

## 2. Scope 选择（最少权限 vs 现有目录）

| Scope | 等级 | 能否写入现有 `Cloud Video Production Studio` | 说明 |
|---|---|---|---|
| `https://www.googleapis.com/auth/drive.file` | 非敏感（最少权限） | **不能**：该目录由另一个应用（Claude Google Drive 连接器）建立；`drive.file` 只能存取本 client 自己建立的、或经 **Google Picker** 授予的文件 | 若选这条：需要 Picker 授权（要额外网页 + API key，本次不建），或由本 client 另建一套新输出目录 |
| `https://www.googleapis.com/auth/drive` | **受限（restricted）** | **能** | 未验证应用会显示「Google 尚未验证此应用」警告；仅供自用（未验证应用上限 100 用户）。依据：[Choose Drive API scopes](https://developers.google.com/workspace/drive/api/guides/api-specific-auth) |

**建议**：要沿用现有输出目录 → `drive`（默认）。若更看重最少权限 → 用 `--scope drive.file`，并接受由新 client 建立一套新输出目录（`studio drive setup`），旧目录保留为连接器交付位置。

> 风险说明：`drive` 授权等于该 Google 账号整个 Drive 的读写权。可随时在 https://myaccount.google.com/permissions 撤销。

## 3. Google Cloud Console 配置清单（账号：yukikimchi2@gmail.com）

**目前进度**：控制台首次使用弹窗停在「Malaysia / Terms of Service / Agree and continue」，**尚未接受条款**。以下步骤需在接受条款后，由你在浏览器完成。**不需要启用试用或计费**：Drive API 免费；若任何页面要求绑定计费或开始试用，请停止并告诉我。

| # | 页面 | 设置 |
|---|---|---|
| 0 | 首次弹窗 | 国家 Malaysia → 阅读并接受 Terms of Service（**由你决定**） |
| 1 | 建立项目：https://console.cloud.google.com/projectcreate | 名称 `dfsc-video-studio`（任意）；组织：No organization |
| 2 | 启用 API：https://console.cloud.google.com/apis/library/drive.googleapis.com | 选刚建的项目 → **Enable**（仅 Google Drive API） |
| 3 | Google Auth Platform → Branding：https://console.cloud.google.com/auth/branding | App name `DFSC Studio Uploader`；User support email = yukikimchi2@gmail.com；Developer contact = 同上 |
| 4 | Audience：https://console.cloud.google.com/auth/audience | User type **External**；Publishing status：要长期无人值守 → **In production**（否则 7 天失效）；若先留 Testing，务必把 yukikimchi2@gmail.com 加入 Test users，且接受 7 天重做 |
| 5 | Data access：https://console.cloud.google.com/auth/scopes | Add scope：`https://www.googleapis.com/auth/drive`（或 `.../drive.file`，见第 2 节）—— 与 bootstrap 的 `--scope` 一致，否则会出现额外警告 |
| 6 | Clients：https://console.cloud.google.com/auth/clients → Create client | **路径 A（推荐）**：Application type **Desktop app**，名称 `dfsc-studio-desktop`。Desktop 不需填 redirect URI，loopback `http://127.0.0.1:<随机端口>` 自动允许。→ 下载 JSON（只存你电脑）。**⟵ 在此停下，由你执行创建** |
|   | 同上 | **路径 B（仅浏览器）**：Application type **Web application**，Authorized redirect URI **精确**为 `https://developers.google.com/oauthplayground`（无结尾斜杠）。**⟵ 在此停下，由你执行创建** |

## 4. 取得 refresh token（一次浏览器授权）

**路径 A：Desktop + loopback（PKCE S256 + state 校验）** —— 在你自己的电脑：
```bash
pip install google-auth-oauthlib
python tools/drive_oauth_bootstrap.py ~/Downloads/client_secret_XXXX.json --write-env ~/dfsc_drive.env
# 浏览器打开 → 以 yukikimchi2@gmail.com 登入 → （未验证警告：Advanced → Go to DFSC Studio Uploader）→ Allow
```
`~/dfsc_drive.env`（权限 600）含 3 个值；复制进云端环境 secret 后删除该文件与 client JSON。

**路径 B：OAuth Playground（自有 Web client）** —— 只用浏览器：
1. 打开 https://developers.google.com/oauthplayground → 右上齿轮 → 勾选 **Use your own OAuth credentials** → 填入 Web client 的 Client ID / Secret；OAuth flow：Server-side；Access type：Offline。
2. 左侧输入 scope `https://www.googleapis.com/auth/drive` → Authorize APIs → 以 yukikimchi2@gmail.com 同意。
3. **Exchange authorization code for tokens** → 复制 Refresh token，直接放进环境 secret（不要贴聊天）。
4. 完成后回到 Clients 页，从该 Web client **移除** Playground redirect URI（Google 建议）。

## 5. 放进云端环境（受控 secret）

Claude 云端：会话标题栏 → 环境选单 → **Default** → Edit → 环境变量 / Network secrets：

| 变量 | 值 |
|---|---|
| `STUDIO_DRIVE_OAUTH_CLIENT_ID` | `…apps.googleusercontent.com` |
| `STUDIO_DRIVE_OAUTH_CLIENT_SECRET` | client secret |
| `STUDIO_DRIVE_OAUTH_REFRESH_TOKEN` | refresh token |
| `STUDIO_DRIVE_OAUTH_SCOPE` | 仅在选 `drive.file` 时设定 |

网络：容器已可连 `oauth2.googleapis.com`（token 刷新）与 `www.googleapis.com/upload`（上传）—— 2026-10-19 实测可达。开一个**新会话**让变量生效。

## 6. 验收（新会话中执行）

```bash
studio drive auth                       # 只显示来源、账号、scope；不显示任何值
studio drive bigtest --folder 1a2f5BEUMFZS0TFQ1L1RvKbjoNty6mB__
#   → 上传 ~26 MB 合成 TEST 影片（新文件名，不覆盖）→ 第一块后故意中断 → 断点续传
#   → 串流下载 → 本地 / Drive / 下载 MD5 三者比对 → ffprobe + 完整解码 → passed: true/false
studio queue run --upload               # 之后渲染完成的 Preview 自动上传到 06_Project_Previews/dfsc-2027
```

## 7. 上传器实作要点（`studio/storage/resumable.py`）

- Drive resumable 协议：POST 建立会话 → 8 MiB（256 KiB 整数倍）区块 PUT → 308/Range 进度 → 200/201 完成。
- **会话 URI 持久化**到 `workspace/uploads/*.json`：程序中断或容器重启后，先以 `Content-Range: bytes */total` 查询已收到的字节，从断点续传；会话过期（404/410）自动重开。
- 只在内存保留一个区块；网络错误 / 5xx 指数退避重试；完成后比对 `md5Checksum`。
- 下载以 HTTP Range 串流写入 `.partial`，可断点续传，完成后 MD5 校验，失败改名 `.corrupt`。
- 本地模拟端点验证（**非 Google**）：26 MB 合成影片，第 1 块后中断 → 同一会话续传 → MD5 一致 → 完整解码（`studio drive bigtest --fake`）。
