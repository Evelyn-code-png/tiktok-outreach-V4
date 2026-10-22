# V4：Google 授权与团队 AI 接入

代码已支持两种新接入方式，但下载代码不等于已开通外部服务。现有 SMTP、个人 AI key 和手动草稿流程保留。Google 与 AI 的真实联调需要以下团队配置；本次自动化测试使用模拟服务，没有发送真实邮件。

## Google：团队配置一次，成员连接自己的账号

1. 在团队的 Google Cloud 项目启用 Gmail API，配置 OAuth consent screen。
2. 创建 **Desktop app** 类型 OAuth client，下载 JSON；不要使用 Web application 类型。
3. 把 JSON 放在项目根目录，命名为 `google-client.json`，或者用 `GOOGLE_OAUTH_CLIENT_FILE` 指定绝对路径。该文件已加入 `.gitignore`。每份本地安装都需要这个团队客户端配置，但成员不用自行创建 Cloud 项目。桌面客户端的 client ID/secret 不是保护团队计费密钥的方法。
4. 测试阶段将参与测试的 Google 账号加入测试用户；Google 测试模式的刷新令牌可能短期失效，届时重新连接。正式对外开放需按申请的 scope 完成适用的验证；读取邮件属于受限权限，服务端处理相关数据可能触发额外评估。
5. 打开 Account Setup，点 **Connect Google**。只发送时不勾选回复读取；需要追踪时勾选 **Also allow Gmail reply access** 并重新连接。桌面应用不依赖增量授权，此流程重新请求完整的选定权限。
6. Google 页面成功后返回工作区。成功连接会把 Sending Gmail 更新为 Google 验证的邮箱。到 Delivery log 点击 **Enable reply tracking** 才开始读取；Google 授权本身不自动启动读取。

实现使用 PKCE S256、随机且十分钟过期的一次性 state、loopback callback 和 refresh token。令牌仅写入原有私有数据目录中的 `google-token.json`，POSIX 文件权限为 0600，不返回前端。Windows 部署需使用适当的用户目录 ACL。请勿复制该令牌文件给其他成员。

Disconnect Google locally 会移除本地令牌并停用该连接，已有回复保留，不会自动切换到旧 SMTP 密码。在 Google Account 的第三方连接设置里撤销应用，才能撤销 Google 侧授权。重新保存应用专属密码会显式切换到 SMTP 备用模式。

Gmail API 发信记录使用 `accepted_by_gmail_api`。它只表示 Gmail 接受发送，不保证进入收件箱；网络中断导致结果不确定时不会自动重发。勿联系名单、预览确认和重复发送保护仍有效。切换 Google 账号或重连会使旧的读取同意失效。

回复读取最多匹配最近 300 封已发送邮件，按联系人和发送时间查询候选邮件，再检查 RFC `In-Reply-To` / `References` 与发件人。仅匹配的邮件读取正文；不标记已读，不删除邮件。API 模式包含 Spam/Trash，SMTP/IMAP 备用模式保持原来的文件夹范围。候选邮件超过 1000 封会停止并提示，不静默截断。

## 团队 AI：后端保管 OpenAI key

新增 `scripts/ai_gateway.py` 是小团队试用的服务端入口。成员填写团队 URL 与个人访问码，不需要创建 OpenAI API key 或填写模型。团队仍承担 OpenAI 费用。此服务不是完整的多租户商业产品：未提供账号注册、管理员界面或分布式限流。

团队管理员在**独立服务器**的环境变量/秘密管理服务中配置：

- `OPENAI_API_KEY`：团队 OpenAI key，只保存在服务器。
- `OPENAI_MODEL`：团队已开通并支持现有结构化输出的模型。
- `AI_GATEWAY_TOKENS`：以逗号分隔的高熵访问码，建议每人不同。可用 `python3 -c 'import secrets; print(secrets.token_urlsafe(32))'` 生成。
- `AI_DAILY_REQUEST_LIMIT`：每个访问码每天请求上限，默认 50，以 UTC 日切分。
- `AI_GATEWAY_DB`：持久化 SQLite 用量文件路径，默认 `~/.config/outreach-ai/usage.sqlite`。备份并保留此文件，避免重启或重新部署重置用量。
- `AI_GATEWAY_PORT`：默认 8766。

配置后运行 `python3 scripts/ai_gateway.py`。服务仅监听 `127.0.0.1`，必须由反向代理提供 HTTPS；代理应限制请求体、连接数和超时。不直接对公网暴露 Python HTTP 服务。成员填写的 URL 为 HTTPS 服务根地址，例如 `https://ai.example.com`，客户端会请求 `/v1/responses`。

Account Setup 中填写 **Team AI service URL** 和 **Team access code**，保存后两个 AI 功能都会走团队服务。也可通过成员机器的 `OUTREACH_AI_URL`、`OUTREACH_AI_TOKEN` 环境变量配置。清空团队 URL 切回个人 key 模式（环境变量优先时需先移除环境变量）。换 URL 会清除旧访问码，避免发给新服务。

网关验证访问码、限制单次请求为 100 KB、固定服务端模型、将最大输出设为 2000 tokens，禁用响应存储，不接受工具调用或其他任意 Responses 参数。请求计入额度后，即使上游失败也不退回次数，避免并发或重试绕过限制。额度是请求数而不是美元硬预算；团队还应设置服务商预算提醒并监控实际花费。访问码轮换会产生新额度身份。

AI 输入会经过团队服务器再发送到 OpenAI。当前匹配功能只使用已有品牌资料和创作者资料；此改动不把 Gmail 回复发送给 AI。个人 key 继续直接请求 OpenAI。

## 验证与待完成联调

运行：

```sh
python3 -m unittest discover -s tests -q
node --test tests/test_send_feedback.cjs
```

自动化覆盖 OAuth state 过期/重放、拒绝部分授权、token 刷新、断连、发送去重与勿联系名单、模糊发送结果、回复同意/精确匹配、AI 入口隔离、服务端模型与持久化额度。界面检查使用隔离的临时数据目录，不覆盖已有工作区。

上线前仍需在团队测试账号验证：Google 授权成功/拒绝/撤销、真实 Gmail API 发信与回复同步、团队 HTTPS 代理、有效/无效访问码、真实模型的结构化输出。未配置凭据前，Google 按钮显示未开通，AI 不会伪装成功。

参考：[Google Desktop OAuth](https://developers.google.com/identity/protocols/oauth2/native-app)、[Gmail 发信](https://developers.google.com/workspace/gmail/api/guides/sending)、[Gmail scopes](https://developers.google.com/workspace/gmail/api/auth/scopes)、[OpenAI API 认证](https://developers.openai.com/api/reference/overview)。

## 在本机先接通测试

双击 `Open Local AI.command`（或运行 `python3 scripts/ai_gateway.py --local`），再打开 Dashboard。此模式读取本机原来保存的个人 AI key / 模型，在随机本地端口启动带访问码的网关，并自动保存 URL 与访问码。key 不会写入代码库、命令行或网页。每次重启网关后刷新 Dashboard；关闭网关窗口会停止服务。仅 `http://127.0.0.1:<端口>` 允许本地 HTTP，非本地地址仍必须使用 HTTPS。此模式只供这台电脑使用，不供团队其他电脑连接。

充值前实测：本机已有 key 可以访问生成接口，但服务商返回 `credit_balance_exhausted`（余额不足）。需要在对应 API 账户充值，或在 Account Setup 更新有额度的个人 key，然后重启本地网关。模型列表接口缺少 `api.model.read` 权限不代表生成接口无权限，不需要为此扩大 key 权限。

## 本机 Google 联调结果（2026-10-19）

已为 `kuangxiaoyi11@gmail.com` 完成 Google OAuth，取得发送及只读权限；Gmail profile 接口和 refresh token 刷新均实测成功。回复追踪已启用，首次同步正常结束，但当前没有已发送记录可匹配。本次没有发送真实邮件，因此实际投递和收到回复后的端到端匹配仍待验证。项目保持 External / Testing，仅已加入的测试用户可授权。

## 本机 AI 联调结果（2026-10-19，充值后）

充值后，通过已配置的本机网关调用应用的 `creator_fit.call_model` 与 `personalization.call_ai` 均成功。测试使用明确虚构的 Demo Creator / Demo Reuse 资料；匹配分析通过字段引用校验，邮件生成返回三个开场段落并通过引用 URL 校验。未发送邮件，也未将测试联系人写入工作区。此前的余额不足已解除；可用额度仍取决于 API 账户余额。

## 团队远程 AI 已接通（2026-10-19）

按管理员选择部署 Render Free，无持久化磁盘，免费实例休眠及计数重置限制已接受。本机已切换到云端服务，不再需要启动 Open Local AI.command。组员操作与验证范围见 [团队指南](TEAM_QUICKSTART_CN.md)。原有本机网关启动器仍保留供离线开发配置使用，启动它会把这台电脑切回本机网关。
