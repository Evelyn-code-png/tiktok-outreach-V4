# 本机打开率与点击率

工作区仍运行在本机 `127.0.0.1`。独立 HTTPS 服务接收追踪事件，本机主动拉取结果；服务没有读取本机文件或邮箱的接口。下载此分支不会自动连接任何服务，也不会复制其他成员的连接令牌。

## 日常使用

1. 在 **Account Setup → Open and click tracking** 填写独立服务地址和访问令牌，点击 **Test connection and enable**。服务地址支持 Cloudflare `workers.dev` 或 `pages.dev` 的 HTTPS 地址。
2. 通过本系统直接发送经过确认的邮件。程序先注册随机追踪编号，再提交邮件；注册失败会阻止该封邮件发送。
3. 在 **Delivery log** 查看 Open rate 和 Click rate。点击 **Sync opens and clicks** 可立即同步；页面可见时每两分钟也会尝试同步。
4. **Pause new tracking** 停止添加新的追踪标记并暂停同步，已保存的记录保留。重新启用后可以继续同步。

启用前的邮件、Gmail 网页发送的邮件不含此追踪标记，不能补追踪。分母只包括具有追踪编号且已被发送服务接受的新邮件；没有符合条件的邮件时显示 **No tracked sends**。回复率继续使用原有的回复追踪逻辑。

打开事件依赖邮件图片加载，隐私预加载可能产生打开记录，屏蔽图片可能漏记。安全扫描也可能触发点击。这些指标不能证明真人阅读或访问。每封邮件每类事件只计一次，不统计总浏览次数。

## 独立服务部署

服务源码和 SQLite 表结构位于 `tracking-worker/`，不依赖 Outreach 的联系人或本机数据目录。部署前为团队选择独立的 Cloudflare 项目。

### Workers 方式

在 `tracking-worker/` 使用 Cloudflare 官方 Wrangler 工具创建 D1 数据库并执行 `schema.sql`。将数据库的绑定名称设为 `TRACKING_DB`，在 `wrangler.jsonc` 的 `d1_databases` 中填写该数据库的名称和 ID。通过项目的加密 Secret 设置 `TRACKING_ADMIN_TOKEN`，然后部署 `worker.mjs`。

示例数据库绑定（把示例值换成自己的值）：

```json
{"binding":"TRACKING_DB","database_name":"your-tracking-db","database_id":"YOUR_DATABASE_ID"}
```

`TRACKING_ADMIN_TOKEN` 应为 32 个密码学随机字节的 base64url 编码（43 个字符）。不要使用邮箱密码、Cloudflare 登录密码或其他服务的 API Key。令牌需要分别保存在服务加密设置和本机配置中，不要写进源码或提交到仓库。

### Pages 方式

也可新建独立 Pages 项目，使用 Advanced mode：仅将 `worker.mjs` 复制并命名为 `_worker.js`，与一个不含数据的 `index.html` 一同上传。新建 D1 数据库并执行 `schema.sql`，绑定为 `TRACKING_DB`，添加同名加密 Secret `TRACKING_ADMIN_TOKEN`。绑定或 Secret 修改后重新部署。无需连接 GitHub 仓库，也不要上传整个 Outreach 文件夹。

用本机界面的 **Test connection and enable** 确认 `/v1/health` 的服务类型及数据库可用性后再发送邮件。客户端以 `OutreachV4-Tracking/1.0` 标识自身，保留令牌验证和 HTTPS 证书验证。

## 数据边界

云端数据库只保存随机编号、HTTPS 链接目的地址、首个打开/点击事件和时间。邮箱地址与编号的对应关系保存在本机。注册接口不接收联系人姓名、收件地址、正文、本地路径或邮箱凭证；云端代码没有文件访问或对本机发起连接的功能。链接目的地址会完整保存，因此不要在需要追踪的链接中放入私人信息或秘密查询参数。

本机连接单独保存在应用数据目录的 `cloud-tracking.json`，权限为仅当前用户可读写。状态接口不返回令牌。更新源码不会覆盖原有邮箱或 AI 配置。不要提交该连接文件、数据库、备份、邮件内容或令牌。

云端代码不记录 IP、User-Agent 或请求正文；平台自身仍按其账户配置处理网络访问数据。事件没有自动过期删除功能。

## 验证

```sh
python3 -m unittest discover -s tests -q
node --test tests/test_send_feedback.cjs tracking-worker/test-worker.mjs
```

Python 测试使用隔离临时目录，不发送邮件。Worker 测试使用 Node 自带的 `node:sqlite`（需要支持该模块的 Node 版本），检查管理鉴权、参数边界、事件去重和链接跳转。
