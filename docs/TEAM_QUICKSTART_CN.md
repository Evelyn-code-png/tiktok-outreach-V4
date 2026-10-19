# 组员 pull 后如何使用完整功能

本项目仍在每个人自己的电脑运行。团队仅托管 AI 网关：OpenAI key 留在网关，Gmail 授权和联系人留在各自电脑。当前部署文件已经准备好，但管理员尚未创建云服务；拿到真实团队连接文件前，不能把本机 AI 地址当作远程服务使用。

## 组员操作

1. 拉取包含团队接入功能的版本，安装 Python 3.10+。
2. 从管理员私下领取分配给你的 `team-connection.json`，放在项目根目录。不要提交这个文件；其中的访问码会消耗团队 AI 额度。
3. 双击 `Setup Team.command`（Mac）或 `Setup Team.bat`（Windows）；Linux 运行 `python3 scripts/team_setup.py`。这会把团队 Google 客户端、AI URL 和成员访问码写入本机私有配置目录，不会导入管理员的 Gmail 授权或 OpenAI key。
4. 双击 `Open Dashboard.command` / `.bat`。在 Account Setup 点击 Connect Google，选择已加入测试名单的**自己的邮箱**；要看回复则勾选回复权限。
5. EasyKOL 未由管理员分配时，在 Account Setup 填入自己的 EasyKOL 凭据。仅有 Google / AI 配置不代表能检索真实 KOL。
6. 正常检索、查看匹配理由、生成草稿；发送前检查收件人和正文。Delivery log 中同意回复追踪。所有邮件仍需手动确认发送。

个人 Gmail 权限不能由管理员代为授权。学校 Google 账号也可能受学校管理员策略限制；若禁止此应用，需要使用已获准的个人 Gmail。测试模式下 Google 可能要求定期重新授权。

## 管理员部署 AI

仓库中的 `Dockerfile.ai` 只复制网关脚本，不包含本机配置、Gmail 令牌或 API key。`render.yaml` 提供一个 Starter 服务和 1 GB 持久化磁盘的部署配置，**这是付费配置**，开通前在 Render 页面核对价格。只需 Hobby 工作区，不需要升级 Pro 工作区。

在 Render 连接你有权限的 Git 仓库及包含这些修改的分支，以 Blueprint 部署。秘密环境变量：

- `OPENAI_API_KEY`：团队管理员的有效 key，仅存在 Render 秘密配置。
- `OPENAI_MODEL`：已验证可用的模型名称。
- `AI_GATEWAY_TOKENS`：每名成员一个随机访问码，以逗号分隔。每个码建议使用 `secrets.token_urlsafe(32)` 生成。
- 默认每个访问码每天 50 次请求，失败的上游请求也计数；可调整 `AI_DAILY_REQUEST_LIMIT`。这不是美元预算上限。

部署后 `/healthz` 应返回 `{"status":"ok"}`，但还需要带访问码真实生成测试才能确认 OpenAI 连接。测试完成后才向组员发放 HTTPS 服务地址。Render 免费服务不能保存本项目的 SQLite 额度账本，重启会重置计数，而且闲置会休眠；当前配置选择持久化磁盘，避免把免费临时磁盘当作可靠额度控制。

每位组员的连接文件结构如下（占位值不能直接使用）：

```json
{
  "version": 1,
  "google_client": {"installed": {"client_id": "TEAM_CLIENT.apps.googleusercontent.com", "client_secret": "DESKTOP_CLIENT_VALUE"}},
  "ai_gateway_url": "https://YOUR-SERVICE.onrender.com",
  "ai_gateway_token": "MEMBER_SPECIFIC_RANDOM_ACCESS_CODE"
}
```

Google 配置必须使用团队 Desktop 客户端；原始下载 JSON 的 `installed` 部分可用于上述字段。这不是任何人的 Gmail refresh token。若经账号所有者批准分配 EasyKOL 凭据，可另加 `easykol_email` 与 `easykol_key`；不要擅自共享个人凭据或将它们写进 Git。

不要发送整个个人配置目录。不要添加 `openai_key`、`gmail_app_password` 或 `refresh_token`；导入器会拒绝这些字段。团队连接文件被 Git 忽略；Git pull 只更新程序，成员配置保存在代码目录外。

## 当前验证范围

本机 Google 连接和真实 AI 生成已通过。新增团队导入流程在隔离目录测试，部署文件尚未在 Render 实际构建运行。完成云端部署、分发配置后，还需由至少一名组员在第二台电脑验证搜索、AI 和自己的 Google 连接，才能确认完整交付。
