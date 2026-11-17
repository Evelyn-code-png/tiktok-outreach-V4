# TikTok Outreach：拉取、运行与修改指南

本文面向需要从私有 GitHub 仓库拉取代码、在本机运行插件，或继续开发功能的协作者。

## 1. 前置条件

- macOS、Linux 或 Windows
- Python 3.10 或更高版本
- Git
- 一个 EasyKOL 账号和 API Key
- 如果使用 Gmail 浏览器发送：已登录 Gmail 的浏览器会话
- 如果使用 SMTP：Gmail 应用专用密码或兼容的 SMTP 凭证

EasyKOL API Key、Gmail 应用专用密码、搜索结果、活动文件和本地数据库都属于运行时数据，不能提交到 GitHub。

## 2. 拉取私有仓库

先确认自己已被授予该私有仓库的访问权限，并使用 SSH 或 HTTPS 完成 GitHub 登录。然后执行：

```bash
git clone git@github.com:<你的用户名>/<仓库名>.git
cd <仓库名>
```

如果使用 HTTPS：

```bash
git clone https://github.com/<你的用户名>/<仓库名>.git
cd <仓库名>
```

## 3. 本地运行

插件没有额外的 pip/npm 依赖。可以先运行测试：

```bash
python3 -m unittest discover -s tests -v
```

启动本地工作台：

```bash
python3 scripts/dashboard.py --no-open
```

也可以运行项目根目录的 `Open Dashboard.command`。工作台只监听 `127.0.0.1`，访问链接和令牌会写入：

```text
~/.config/tiktok-outreach/dashboard-session.json
```

在 **Account Setup** 中配置 EasyKOL 邮箱、EasyKOL API Key、发信 Gmail 和可选 SMTP/追踪设置。真实配置保存在 `~/.config/tiktok-outreach/config.json`，不在仓库中。

## 4. 使用流程

1. 在 **Find Creators** 输入达人方向、国家、语言、粉丝范围和预算。
2. 启动搜索，等待任务完成并打开保存的联系人列表。
3. 导入 CSV/XLSX，筛选和选择收件人；需要时批量补全 TikTok 主页邮箱。
4. 在 **Outreach email** 编辑主题和正文。支持 `$name`、`$username`、`$profile_url`。
5. 保存或加载邮件模板，生成草稿并核对每位收件人。
6. 使用 Gmail 浏览器模式或配置后的 SMTP 发送。
7. 在 **Delivery log** 查看发送状态和统计。打开/点击追踪需要公开 HTTPS tracking URL；回复统计需要邮件系统调用 reply webhook。

## 5. 命令行开发入口

```bash
python3 scripts/outreach.py doctor
python3 scripts/outreach.py quota
python3 scripts/outreach.py search --query "beauty creators" --regions US --languages en --limit 20 --budget 20 --out ./search-run
python3 scripts/outreach.py draft --csv ./search-run/creators.csv --subject 'Collaboration with $name' --body ./body.txt --out ./campaign.json
python3 scripts/outreach.py history
```

邮箱补全使用 `emails-start` 和 `emails-collect`。浏览器 Gmail 发送使用 `browser-plan`、`browser-claim` 和 `browser-result`。SMTP 默认只预览，只有在明确提供 `--execute` 和活动 ID 时才会实际发送。

## 6. 修改代码

- `assets/index.html`：工作台结构和文案。
- `assets/app.css`：视觉样式和响应式布局。
- `assets/app.js`：前端状态、API 调用、模板、联系人和统计交互。
- `scripts/outreach.py`：EasyKOL、CSV、草稿、SMTP、发送去重和追踪逻辑。
- `scripts/workspace.py`：本地任务、联系人、模板和活动持久化。
- `scripts/dashboard.py`：本地 HTTP API、认证和 tracking endpoints。
- `scripts/email_results.py`：EasyKOL XLSX 结果解析与合并。
- `tests/`：搜索、导入、发送恢复、模板、追踪和安全测试。

建议修改流程：

```bash
git checkout -b codex/<简短功能名>
python3 -m unittest discover -s tests -v
# 修改代码并补充必要测试
node --check assets/app.js
python3 -m py_compile scripts/*.py
git diff --check
git status --short
```

前端改动后刷新本地工作台；后端改动后重启 `dashboard.py`。不要直接修改 `~/.config/tiktok-outreach` 中的 SQLite 或 JSON 来绕过发送保护。

## 7. 提交和推送

```bash
git add .
git commit -m "Describe the change"
git push -u origin codex/<简短功能名>
```

提交前确认：

- `git status --ignored` 中没有待提交的 `config.json`、`runs/`、`campaigns/`、`jobs/`、`templates/`、数据库或日志。
- 没有把 API Key、应用密码、浏览器令牌或真实联系人写入代码、测试和文档。
- 搜索和发送等计费/外部副作用操作有幂等保护和清晰预览。
- unknown 或 sending 状态先核查 Gmail Sent，再决定是否重试。

## 8. 常见故障

- **缺少 EasyKOL Key**：在本机工作台 Account Setup 配置，或运行 `setup`；不要把 Key 发到聊天或提交到仓库。
- **浏览器发送失败**：检查 Gmail 是否登录、From 地址是否匹配，并遵循 `skills/tiktok-outreach/browser-mail.md`。
- **SMTP 认证失败**：使用应用专用密码，不要使用 Gmail 普通登录密码。
- **统计显示 Not enabled**：为 tracking base URL 配置公开 HTTPS 地址；本机 `127.0.0.1` 无法被收件人邮箱访问。
- **任务状态 unknown**：先查看服务商任务或 Gmail Sent，系统不会自动重复可能已经提交的请求。

## 9. 安全边界

本项目是本地单用户工具。它不会绕过 EasyKOL、TikTok 或 Gmail 的访问控制，也不保证邮箱可达、邮件进箱或被阅读。使用批量触达时，应遵守适用的隐私、退订和反垃圾邮件法规及平台条款。
