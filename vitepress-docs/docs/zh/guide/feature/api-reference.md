# API 参考

本页按 `worker/src` 源码整理，覆盖 Worker 对外提供的全部 **133** 个 HTTP 接口，包括 `worker.ts` 中 8 个 `app.route('/', ...)` 挂载模块的注册，以及 `worker.ts` 直接挂载的 `/` 与 `/health_check`。文件末尾的 `app.all('/*')` 只做 404 兜底，不计入接口。

- 「源码」列相对 `worker/src/`，行号是路由注册位置。
- 「鉴权」列只列该接口**自身**的鉴权要求；站点私有密码对所有路径的额外要求见下文。

## 概览

### 请求地址

接口统一挂在 Worker 域名下，例如 `https://your-worker.example.com`。

- 前端默认与页面同源：`pages/functions/_middleware.js` 会把 `/api/`、`/open_api/`、`/user_api/`、`/admin/`、`/telegram/`、`/external/`、`/redeem_api/` 前缀的请求转发到 Worker。
- 前端也可用 `VITE_API_BASE` 指定独立 API 域名；为空时使用同源。
- 下表路径均为完整路径（已含前缀），`<...>` 表示路径参数。

### 鉴权方式

| 方式 | 传递位置 | 说明 |
| --- | --- | --- |
| 地址 JWT | `Authorization: Bearer <address JWT>` | 创建邮箱时返回的 `jwt`，只代表一个邮箱地址；`/api/*` 默认使用 |
| 用户 JWT | `x-user-token: <user JWT>` | `/user_api/login`、`/user_api/register` 等返回，代表用户账户 |
| 用户角色令牌 | `x-user-access-token: <access token>` | 可选凭据：`/user_api/settings` 返回，1 小时有效，携带 `user_role`。不提供时直接放行，提供时校验过期时间与 `user_id`（`worker.ts:135-155`） |
| 管理员密码 | `x-admin-auth: <ADMIN_PASSWORDS 之一>` | `/admin/*`；配置 `ADMIN_USER_ROLE` 时也可用管理员角色的 `x-user-access-token` |
| 站点密码 | `x-custom-auth: <PASSWORDS 之一>` | 配置 `PASSWORDS` 后，除 `/open_api/*`、`/telegram/*` 外所有请求都必需 |
| 语言 | `x-lang: zh` / `en` | 控制错误文本语言，缺省用 `DEFAULT_LANG` |
| Telegram initData | 请求体 `initData` 字段 | `/telegram/*` 小程序接口，用 Bot Token 做 HMAC 校验 |
| 请求体 token | 请求体 `token` 字段 | 仅 `/external/api/send_mail`，用于不便加请求头的场景 |
| 签名 URL | 路径中的 `:expires`、`:signature` | 仅 `/open_api/a/...`，HMAC 签名 + 过期时间 |

::: tip 地址 JWT 与用户 JWT 是两种凭据
地址 JWT 只能访问该邮箱（`/api/*`），用户 JWT 只能访问用户账户（`/user_api/*`）。两者不能互换，详见 [新建邮箱地址 API](./new-address-api.md)。
:::

### 通用约定

- **分页**：列表接口读取 `limit`、`offset`；`limit` 必须为 1–100，`offset` 必须 ≥ 0，否则返回 400。响应为 `{ results, count }`，`count` 只在 `offset=0` 时统计，其余情况返回 0（`worker/src/common.ts:678-714` 的 `handleListQuery`、`716-725` 的 `hideObjectFields`、`730-753` 的 `handleMailListQuery`）。
- **错误文本**：多数错误用 `c.text(...)` 返回纯文本并按 `x-lang` 本地化；部分鉴权错误返回 `{ code, message }` JSON；未捕获异常由全局 `onError` 返回 `{ code: "INTERNAL_SERVER_ERROR", message }` 与 500。
- **限流与访问控制**：`/api/new_address`、`/api/send_mail`、`/external/api/send_mail`、`/user_api/address/:address_id/send_mail`、`/user_api/register`、`/user_api/verify_code`、`/redeem_api/*` 会先经过 `RATE_LIMITER` 限流（超限 429）以及 IP 黑名单、每日限额检查。

### 错误码

`worker/src/error_codes.ts` 定义 4 个 JSON 错误码：

| code | 触发场景 |
| --- | --- |
| `INTERNAL_SERVER_ERROR` | 未捕获异常，返回 500 |
| `AUTH_SITE_PASSWORD_INVALID` | 站点密码缺失或错误 |
| `AUTH_ADMIN_CREDENTIAL_INVALID` | 管理员凭据无效，或用户角色不是管理员 |
| `AUTH_USER_ACCESS_TOKEN_EXPIRED` | `x-user-access-token` 已过期 |

常用 HTTP 状态码：

| 状态码 | 含义 | 典型返回 |
| --- | --- | --- |
| 400 | 参数缺失、非法，或环境变量未配置 | `DBNotAvailableMsg`、`JWTSecretNotSetMsg`、`DomainsNotSetMsg`、`InvalidLimitMsg` |
| 401 | 鉴权失败 | `AUTH_*` JSON 或 `InvalidAddressCredentialMsg`、`UserTokenExpiredMsg` |
| 403 | 功能未启用或无权限 | `ENABLE_*` 关闭、IP 白名单、Webhook 允许列表 |
| 404 | 路由不存在，或兑换码功能未启用 | Hono 默认 `404 Not Found`（`c.notFound()`，如兑换码关闭时）与兜底 `Not Found`（`app.all('/*')`，`worker.ts:316`） |
| 409 | 兑换码并发冲突，或用户已有其他角色 | `RedeemCodeUnavailableMsg`、`RedeemRoleConflictMsg`（`redeem_code.ts:226`） |
| 429 | 触发限流 | `IP=<ip> Rate limit exceeded for <path>` |
| 500 | 服务端异常 | `{ code: "INTERNAL_SERVER_ERROR", message }` |

## 接口统计

| 模块 | 接口数 |
| --- | --- |
| 公共 / Open API | 5 |
| 邮箱地址 API | 23 |
| 发信 API | 5 |
| 用户 API | 26 |
| 管理 API | 59 |
| Telegram | 10 |
| 兑换码 | 3 |
| 根路径 | 2 |
| **合计** | **133** |

## 公共 / Open API（5）

不要求会话凭据，也不受站点私有密码限制；其中 `/open_api/a/...` 依赖签名 URL 鉴权。

| 方法 | 路径 | 鉴权 | 源码 | 说明 |
| --- | --- | --- | --- | --- |
| `GET` | `/open_api/settings` | 无 | `commom_api.ts:11` | 返回前端启动所需公开配置：标题、公告、域名、功能开关、SMTP/IMAP 代理与版本号，并用 `needAuth` 告知是否启用站点密码 |
| `GET` | `/open_api/a/:mail_id/:index/:expires/:signature` | 签名 URL | `commom_api.ts:79` | 按 Webhook 附件签名下载指定邮件第 `index` 个附件；校验 HMAC 与过期时间，且需 `ENABLE_WEBHOOK` |
| `POST` | `/open_api/site_login` | 无 | `open_api/auth.ts:10` | 校验站点私有密码（`PASSWORDS`，可带 Turnstile），成功返回 `{ success: true }` |
| `POST` | `/open_api/admin_login` | 无 | `open_api/auth.ts:28` | 校验管理员密码（`ADMIN_PASSWORDS`），成功返回 `{ success: true }` |
| `POST` | `/open_api/credential_login` | 无 | `open_api/auth.ts:46` | 校验地址 JWT 并确认地址仍存在，成功返回 `{ success: true }` |

## 邮箱地址 API（23）

以地址 JWT 为主体，`/api/*` 由 `worker.ts:158` 的中间件统一鉴权；下表「鉴权」列标出了例外接口。

| 方法 | 路径 | 鉴权 | 源码 | 说明 |
| --- | --- | --- | --- | --- |
| `GET` | `/api/auto_reply` | 地址 JWT | `mails_api/index.ts:14` | 读取当前地址的自动回复配置（主题、正文、启用状态、前缀、名称），未配置返回 `{}`；需 `ENABLE_AUTO_REPLY` |
| `POST` | `/api/auto_reply` | 地址 JWT | `mails_api/index.ts:15` | 保存自动回复配置，启用时主题与正文必填且均不超过 255 字符；需 `ENABLE_AUTO_REPLY` |
| `GET` | `/api/webhook/settings` | 地址 JWT | `mails_api/index.ts:18` | 读取当前地址的 Webhook 设置；管理员开启允许列表且地址不在其中时返回 403 |
| `POST` | `/api/webhook/settings` | 地址 JWT | `mails_api/index.ts:19` | 保存当前地址的 Webhook 设置，保存前编译校验过滤规则 |
| `POST` | `/api/webhook/test` | 地址 JWT | `mails_api/index.ts:20` | 用随机或指定 `mail_id` 的邮件，向配置的 URL 实际发送一次测试 Webhook |
| `POST` | `/api/webhook/check_filter` | 地址 JWT | `mails_api/index.ts:21` | 用随机或指定邮件校验过滤规则是否命中，返回 `matched` |
| `GET` | `/api/attachment/list` | 地址 JWT | `mails_api/index.ts:24` | 列出 S3 中当前地址前缀下的附件 key；需配置 S3 变量 |
| `POST` | `/api/attachment/delete` | 地址 JWT | `mails_api/index.ts:25` | 删除 S3 中当前地址的指定附件 key |
| `POST` | `/api/attachment/put_url` | 地址 JWT | `mails_api/index.ts:26` | 为当前地址生成上传（PUT）预签名 URL |
| `POST` | `/api/attachment/get_url` | 地址 JWT | `mails_api/index.ts:27` | 为当前地址生成下载（GET）预签名 URL |
| `GET` | `/api/mails` | 地址 JWT | `mails_api/index.ts:30` | 分页列出当前地址的收件（`raw_mails`） |
| `GET` | `/api/mail/:mail_id` | 地址 JWT | `mails_api/index.ts:31` | 取当前地址单封邮件的原始内容，不存在返回 `null` |
| `DELETE` | `/api/mails/:id` | 地址 JWT | `mails_api/index.ts:32` | 删除当前地址的一封邮件；需 `ENABLE_USER_DELETE_EMAIL` |
| `PATCH` | `/api/mails/:id/read` | 地址 JWT | `mails_api/index.ts:33` | 设置邮件已读/未读（请求体 `isUnread`）；需 `ENABLE_MAIL_READ_STATUS` |
| `GET` | `/api/parsed_mails` | 地址 JWT | `mails_api/index.ts:36` | 分页列出收件，并在服务端解析出 sender、subject、text、html 与附件元数据 |
| `GET` | `/api/parsed_mail/:mail_id` | 地址 JWT | `mails_api/index.ts:37` | 单封邮件的服务端解析结果 |
| `GET` | `/api/settings` | 地址 JWT（可选角色令牌） | `mails_api/index.ts:40` | 返回当前地址与发信余额 `{ address, send_balance }`，并刷新地址活跃时间 |
| `POST` | `/api/new_address` | 可选用户 JWT | `mails_api/index.ts:41` | 创建新邮箱地址并返回 `{ jwt, address, address_id }`；受创建开关、Turnstile、地址黑名单与限流约束 |
| `DELETE` | `/api/delete_address` | 地址 JWT | `mails_api/index.ts:42` | 删除当前地址及其邮件、发件记录与绑定关系；`ENABLE_USER_DELETE_EMAIL` 关闭时抛错，由全局 `onError` 返回 500 |
| `DELETE` | `/api/clear_inbox` | 地址 JWT | `mails_api/index.ts:43` | 清空当前地址收件箱；需 `ENABLE_USER_DELETE_EMAIL` |
| `DELETE` | `/api/clear_sent_items` | 地址 JWT | `mails_api/index.ts:44` | 清空当前地址发件箱；需 `ENABLE_USER_DELETE_EMAIL` |
| `POST` | `/api/address_change_password` | 地址 JWT | `mails_api/index.ts:47` | 修改当前地址密码（直接存前端 SHA-256 哈希）；需 `ENABLE_ADDRESS_PASSWORD` |
| `POST` | `/api/address_login` | 无（地址 JWT 例外） | `mails_api/index.ts:48` | 用邮箱名 + 密码换取地址 JWT；需 `ENABLE_ADDRESS_PASSWORD` |

## 发信 API（5）

发信通道由 `SEND_MAIL` 绑定、Resend 或 SMTP 决定，并受发信余额与限额约束。

| 方法 | 路径 | 鉴权 | 源码 | 说明 |
| --- | --- | --- | --- | --- |
| `POST` | `/api/request_send_mail_access` | 地址 JWT | `mails_api/send_mail_api.ts:18` | 当前地址申请发信权限，写入待审批记录；重复申请返回 400 |
| `POST` | `/api/send_mail` | 地址 JWT（可选角色令牌） | `mails_api/send_mail_api.ts:251` | 用当前地址发送邮件，成功后写入发件箱（sendbox），失败返回 400 |
| `POST` | `/external/api/send_mail` | 请求体 `token` | `mails_api/send_mail_api.ts:263` | 外部系统发信：地址 JWT 放在请求体 `token`，无需 Authorization 头 |
| `GET` | `/api/sendbox` | 地址 JWT | `mails_api/send_mail_api.ts:291` | 分页列出当前地址的发件箱 |
| `DELETE` | `/api/sendbox/:id` | 地址 JWT | `mails_api/send_mail_api.ts:297` | 删除当前地址的一条发件记录；需 `ENABLE_USER_DELETE_EMAIL` |

## 用户 API（26）

以用户 JWT 为主体，`/user_api/*` 由 `worker.ts:185` 的中间件统一鉴权；`DISABLE_USER_SYSTEM` 打开时整组接口返回 403。

| 方法 | 路径 | 鉴权 | 源码 | 说明 |
| --- | --- | --- | --- | --- |
| `GET` | `/user_api/open_settings` | 无 | `user_api/index.ts:14` | 公开用户系统配置：是否启用、是否需邮箱验证、OAuth2 客户端列表 |
| `GET` | `/user_api/settings` | 用户 JWT | `user_api/index.ts:15` | 返回用户信息、角色、管理员标记、1 小时 `access_token`，以及临近过期时的新 `new_user_token` |
| `GET` | `/user_api/mails` | 用户 JWT | `user_api/index.ts:18` | 分页列出当前用户全部绑定邮箱的收件，可用 `address` 过滤 |
| `DELETE` | `/user_api/mails/:id` | 用户 JWT | `user_api/index.ts:19` | 删除当前用户绑定邮箱中的一封邮件；需 `ENABLE_USER_DELETE_EMAIL` |
| `GET` | `/user_api/address/:address_id/settings` | 用户 JWT（可选角色令牌） | `user_api/index.ts:22` | 返回已绑定邮箱地址与发信余额 |
| `POST` | `/user_api/address/:address_id/request_send_mail_access` | 用户 JWT（可选角色令牌） | `user_api/index.ts:23` | 为已绑定邮箱申请发信权限 |
| `POST` | `/user_api/address/:address_id/send_mail` | 用户 JWT（可选角色令牌） | `user_api/index.ts:24` | 用已绑定邮箱发信，成功后写入发件箱 |
| `GET` | `/user_api/sendbox` | 用户 JWT | `user_api/index.ts:25` | 分页列出当前用户绑定邮箱的发件箱，可用 `address` 过滤 |
| `DELETE` | `/user_api/sendbox/:mail_id` | 用户 JWT | `user_api/index.ts:26` | 删除当前用户绑定邮箱的一条发件记录；需 `ENABLE_USER_DELETE_EMAIL` |
| `POST` | `/user_api/login` | 无 | `user_api/index.ts:29` | 邮箱 + 密码登录，返回 30 天有效的用户 JWT |
| `POST` | `/user_api/verify_code` | 无 | `user_api/index.ts:30` | 向注册邮箱发送 6 位验证码（KV 保存 5 分钟），受 Turnstile 与邮箱域名白名单约束 |
| `POST` | `/user_api/register` | 无 | `user_api/index.ts:31` | 用邮箱、密码与验证码注册用户；需在管理端启用用户系统 |
| `GET` | `/user_api/oauth2/login_url` | 无 | `user_api/index.ts:34` | 按 `clientID` 生成第三方 OAuth2 授权跳转 URL |
| `POST` | `/user_api/oauth2/callback` | 无 | `user_api/index.ts:35` | 用授权 `code` 换取 access token、拉取用户信息并登录或注册 |
| `GET` | `/user_api/bind_address` | 用户 JWT（可选角色令牌） | `user_api/index.ts:38` | 分页列出当前用户已绑定邮箱，含邮件数与发件数，支持 `query` 关键字过滤 |
| `POST` | `/user_api/bind_address` | 用户 JWT（可选角色令牌）+ 地址 JWT | `user_api/index.ts:39` | 把地址 JWT 对应的邮箱绑定到当前用户，同时校验绑定数量上限 |
| `GET` | `/user_api/bind_address_jwt/:address_id` | 用户 JWT（可选角色令牌） | `user_api/index.ts:40` | 为已绑定邮箱签发地址 JWT |
| `POST` | `/user_api/unbind_address` | 用户 JWT | `user_api/index.ts:41` | 解绑当前用户的指定邮箱 |
| `POST` | `/user_api/transfer_address` | 用户 JWT | `user_api/index.ts:42` | 把邮箱转移给另一个用户，重建地址行并转移绑定 |
| `GET` | `/user_api/passkey` | 用户 JWT | `user_api/index.ts:45` | 列出当前用户的 passkey |
| `POST` | `/user_api/passkey/rename` | 用户 JWT | `user_api/index.ts:46` | 重命名 passkey，名称不超过 255 字符 |
| `DELETE` | `/user_api/passkey/:passkey_id` | 用户 JWT | `user_api/index.ts:47` | 删除当前用户的指定 passkey |
| `POST` | `/user_api/passkey/register_request` | 用户 JWT | `user_api/index.ts:48` | 生成 passkey 注册 challenge（WebAuthn options） |
| `POST` | `/user_api/passkey/register_response` | 用户 JWT | `user_api/index.ts:49` | 校验并保存 passkey 注册结果 |
| `POST` | `/user_api/passkey/authenticate_request` | 无 | `user_api/index.ts:50` | 生成 passkey 登录 challenge |
| `POST` | `/user_api/passkey/authenticate_response` | 无 | `user_api/index.ts:51` | 校验 passkey 断言，成功后返回用户 JWT |

## 管理 API（59）

`/admin/*` 由 `worker.ts:235` 的中间件统一鉴权：`x-admin-auth` 命中 `ADMIN_PASSWORDS`，或 `x-user-access-token` 的角色等于 `ADMIN_USER_ROLE`；配置 `ADMIN_API_IP_WHITELIST` 时还会校验来源 IP。

### 邮箱地址

| 方法 | 路径 | 鉴权 | 源码 | 说明 |
| --- | --- | --- | --- | --- |
| `GET` | `/admin/address` | 管理员 | `admin_api/index.ts:26` | 分页列出全部邮箱地址，支持关键字搜索、排序与邮件/发件计数，响应隐藏密码 |
| `POST` | `/admin/new_address` | 管理员 | `admin_api/index.ts:27` | 管理员创建邮箱地址（跳过域名白名单与长度校验），返回地址 JWT |
| `DELETE` | `/admin/delete_address/:id` | 管理员 | `admin_api/index.ts:28` | 删除地址并在单事务中级联清理邮件、发件、发信权限、自动回复与用户绑定 |
| `DELETE` | `/admin/clear_inbox/:id` | 管理员 | `admin_api/index.ts:29` | 清空指定地址的收件箱 |
| `DELETE` | `/admin/clear_sent_items/:id` | 管理员 | `admin_api/index.ts:30` | 清空指定地址的发件箱 |
| `GET` | `/admin/show_password/:id` | 管理员 | `admin_api/index.ts:31` | 为指定地址签发地址 JWT（控制台「查看密码」） |
| `POST` | `/admin/address/:id/reset_password` | 管理员 | `admin_api/index.ts:32` | 重置地址密码（存前端 SHA-256 哈希）；需 `ENABLE_ADDRESS_PASSWORD` |

### 邮件

| 方法 | 路径 | 鉴权 | 源码 | 说明 |
| --- | --- | --- | --- | --- |
| `GET` | `/admin/mails` | 管理员 | `admin_api/index.ts:35` | 分页列出全部邮件，可用 `address` 过滤 |
| `GET` | `/admin/mails_unknow` | 管理员 | `admin_api/index.ts:36` | 分页列出地址不存在的「未知邮件」 |
| `GET` | `/admin/mails/:id` | 管理员 | `admin_api/index.ts:37` | 按 ID 读取任意一封邮件 |
| `DELETE` | `/admin/mails/:id` | 管理员 | `admin_api/index.ts:38` | 按 ID 删除任意一封邮件 |

### 发信权限与发件箱

| 方法 | 路径 | 鉴权 | 源码 | 说明 |
| --- | --- | --- | --- | --- |
| `GET` | `/admin/address_sender` | 管理员 | `admin_api/index.ts:41` | 分页列出地址发信权限与余额记录，可用 `address` 过滤 |
| `POST` | `/admin/address_sender` | 管理员 | `admin_api/index.ts:42` | 更新指定地址的发信启用状态与余额，并向该地址发送站内通知邮件 |
| `DELETE` | `/admin/address_sender/:id` | 管理员 | `admin_api/index.ts:43` | 删除一条发信权限记录 |
| `GET` | `/admin/sendbox` | 管理员 | `admin_api/index.ts:46` | 分页列出全部发件箱记录，可用 `address` 过滤 |
| `DELETE` | `/admin/sendbox/:id` | 管理员 | `admin_api/index.ts:47` | 删除一条发件箱记录 |

### 统计与全局名单

| 方法 | 路径 | 鉴权 | 源码 | 说明 |
| --- | --- | --- | --- | --- |
| `GET` | `/admin/statistics` | 管理员 | `admin_api/index.ts:50` | 返回邮件、地址、7/30 天活跃地址、用户与发件总数 |
| `GET` | `/admin/account_settings` | 管理员 | `admin_api/index.ts:53` | 读取地址黑名单、发信黑名单、已验证地址、发件人黑名单、邮件规则与发信限额配置 |
| `POST` | `/admin/account_settings` | 管理员 | `admin_api/index.ts:54` | 保存上述全局名单与规则 |
| `POST` | `/admin/cleanup` | 管理员 | `admin_api/index.ts:57` | 按 `cleanType`、`cleanDays` 手动清理历史数据 |
| `GET` | `/admin/auto_cleanup` | 管理员 | `admin_api/index.ts:58` | 读取自动清理配置 |
| `POST` | `/admin/auto_cleanup` | 管理员 | `admin_api/index.ts:59` | 保存自动清理配置，并校验自定义 SQL 清理语句 |

### 用户管理

| 方法 | 路径 | 鉴权 | 源码 | 说明 |
| --- | --- | --- | --- | --- |
| `GET` | `/admin/user_settings` | 管理员 | `admin_api/index.ts:62` | 读取用户系统设置：是否启用、邮箱验证、最大地址数等 |
| `POST` | `/admin/user_settings` | 管理员 | `admin_api/index.ts:63` | 保存用户系统设置，校验验证发件邮箱域名与地址数上限 |
| `GET` | `/admin/users` | 管理员 | `admin_api/index.ts:64` | 分页列出用户，支持邮箱搜索，含角色与绑定地址数 |
| `DELETE` | `/admin/users/:user_id` | 管理员 | `admin_api/index.ts:65` | 删除用户并清理其地址绑定 |
| `POST` | `/admin/users` | 管理员 | `admin_api/index.ts:66` | 管理员创建用户（邮箱 + 密码） |
| `POST` | `/admin/users/:user_id/reset_password` | 管理员 | `admin_api/index.ts:67` | 重置指定用户的密码 |
| `GET` | `/admin/user_roles` | 管理员 | `admin_api/index.ts:68` | 返回 `USER_ROLES` 配置的角色列表 |
| `POST` | `/admin/user_roles` | 管理员 | `admin_api/index.ts:69` | 设置或清除指定用户的角色 |
| `GET` | `/admin/role_address_config` | 管理员 | `admin_api/index.ts:70` | 读取按角色配置的地址数量上限 |
| `POST` | `/admin/role_address_config` | 管理员 | `admin_api/index.ts:71` | 保存按角色配置的地址数量上限 |
| `GET` | `/admin/users/bind_address/:user_id` | 管理员 | `admin_api/index.ts:72` | 列出指定用户已绑定的邮箱 |
| `POST` | `/admin/users/bind_address` | 管理员 | `admin_api/index.ts:73` | 把邮箱绑定到用户，可传 `user_email`/`address` 或对应 ID |

### 第三方登录、Webhook 与 Worker 配置

| 方法 | 路径 | 鉴权 | 源码 | 说明 |
| --- | --- | --- | --- | --- |
| `GET` | `/admin/user_oauth2_settings` | 管理员 | `admin_api/index.ts:76` | 读取 OAuth2 提供商配置列表 |
| `POST` | `/admin/user_oauth2_settings` | 管理员 | `admin_api/index.ts:77` | 保存 OAuth2 配置，逐项校验必填字段 |
| `GET` | `/admin/webhook/settings` | 管理员 | `admin_api/index.ts:80` | 读取 Webhook 全局允许列表设置 |
| `POST` | `/admin/webhook/settings` | 管理员 | `admin_api/index.ts:81` | 保存 Webhook 全局允许列表设置 |
| `GET` | `/admin/mail_webhook/settings` | 管理员 | `admin_api/index.ts:84` | 读取全局邮件 Webhook 设置 |
| `POST` | `/admin/mail_webhook/settings` | 管理员 | `admin_api/index.ts:85` | 保存全局邮件 Webhook 设置，保存前校验过滤规则 |
| `POST` | `/admin/mail_webhook/test` | 管理员 | `admin_api/index.ts:86` | 用随机或指定邮件向全局 Webhook 发送测试请求 |
| `POST` | `/admin/mail_webhook/check_filter` | 管理员 | `admin_api/index.ts:87` | 校验全局 Webhook 过滤规则是否命中 |
| `GET` | `/admin/worker/configs` | 管理员 | `admin_api/index.ts:90` | 返回 Worker 环境变量配置快照，密码与密钥只暴露数量或布尔值 |

### 发信、数据库与通用配置

| 方法 | 路径 | 鉴权 | 源码 | 说明 |
| --- | --- | --- | --- | --- |
| `POST` | `/admin/send_mail` | 管理员 | `admin_api/index.ts:93` | 管理员以任意 `from_mail` 发信，跳过余额与地址归属检查，但仍校验发件域名、发信黑名单与发信通道 |
| `POST` | `/admin/send_mail_by_binding` | 管理员 | `admin_api/index.ts:94` | 通过 `SEND_MAIL` 绑定直接发送原始邮件，校验发件域已启用绑定发信；未绑定 `SEND_MAIL` 返回 400 |
| `GET` | `/admin/db_version` | 管理员 | `admin_api/index.ts:97` | 返回当前/代码 DB 版本、是否需初始化或迁移、数据库大小 |
| `POST` | `/admin/db_initialize` | 管理员 | `admin_api/index.ts:98` | 执行建表 SQL 并写入 DB 版本 |
| `POST` | `/admin/db_migration` | 管理员 | `admin_api/index.ts:99` | 按版本顺序执行增量迁移 |
| `GET` | `/admin/config/:key` | 管理员 | `admin_api/index.ts:102` | 读取一个通用管理配置项，key 需匹配 `[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}` |
| `POST` | `/admin/config` | 管理员 | `admin_api/index.ts:103` | 保存一个通用管理配置项，`value` 必须是字符串 |

### 兑换码管理

未启用 `ENABLE_REDEEM_CODE` 时这一组接口返回 404。

| 方法 | 路径 | 鉴权 | 源码 | 说明 |
| --- | --- | --- | --- | --- |
| `GET` | `/admin/redeem_codes` | 管理员 | `admin_api/index.ts:108` | 按 `redeem_type` 分页列出兑换码，支持 code 关键字搜索，结果字段解密 |
| `GET` | `/admin/redeem_codes/export` | 管理员 | `admin_api/index.ts:109` | 按类型导出兑换码 CSV（含业务列），`limit` 有上限 |
| `POST` | `/admin/redeem_codes/batch` | 管理员 | `admin_api/index.ts:110` | 批量生成兑换码（UUID v4），返回本次生成的 code 列表 |
| `PUT` | `/admin/redeem_codes/:id` | 管理员 | `admin_api/index.ts:111` | 更新兑换码的类型、值、启用状态或有效期 |
| `DELETE` | `/admin/redeem_codes/:id` | 管理员 | `admin_api/index.ts:112` | 删除兑换码 |

### IP 黑名单与 AI 识别

| 方法 | 路径 | 鉴权 | 源码 | 说明 |
| --- | --- | --- | --- | --- |
| `GET` | `/admin/ip_blacklist/settings` | 管理员 | `admin_api/index.ts:115` | 读取 IP 黑名单、ASN/指纹黑名单、白名单与每日限额设置 |
| `POST` | `/admin/ip_blacklist/settings` | 管理员 | `admin_api/index.ts:116` | 保存并逐字段校验 IP 黑名单设置 |
| `GET` | `/admin/ai_extract/settings` | 管理员 | `admin_api/index.ts:119` | 读取 AI 邮件识别的允许列表设置 |
| `POST` | `/admin/ai_extract/settings` | 管理员 | `admin_api/index.ts:120` | 保存 AI 邮件识别的允许列表设置 |

## Telegram（10）

`/telegram/*` 由 `worker.ts` 全局中间件跳过站点密码，但 `telegram_api/index.ts:13` 会要求配置 `TELEGRAM_BOT_TOKEN` 与 `KV`，否则返回 400；`/admin/telegram/*` 还需通过管理 API 鉴权。

| 方法 | 路径 | 鉴权 | 源码 | 说明 |
| --- | --- | --- | --- | --- |
| `POST` | `/telegram/webhook` | 无（依赖 URL 保密，见附注） | `telegram_api/index.ts:35` | Telegram Bot Webhook 入口，把 update 交给 Telegraf 处理 |
| `POST` | `/admin/telegram/init` | 管理员 | `telegram_api/index.ts:50` | 把当前域名下的 `/telegram/webhook` 注册为 Bot Webhook，并初始化命令 |
| `GET` | `/admin/telegram/status` | 管理员 | `telegram_api/index.ts:63` | 返回 Bot 的 Webhook 信息与已注册命令 |
| `GET` | `/admin/telegram/settings` | 管理员 | `telegram_api/index.ts:71` | 读取 Telegram 设置：允许列表、Mini App URL、全局推送列表 |
| `POST` | `/admin/telegram/settings` | 管理员 | `telegram_api/index.ts:72` | 保存 Telegram 设置 |
| `POST` | `/telegram/get_bind_address` | TG initData | `telegram_api/index.ts:73` | 返回当前 Telegram 用户已绑定的邮箱及其地址 JWT |
| `POST` | `/telegram/new_address` | TG initData | `telegram_api/index.ts:74` | 为当前 Telegram 用户创建并绑定新邮箱地址 |
| `POST` | `/telegram/bind_address` | TG initData | `telegram_api/index.ts:75` | 用地址 JWT 把邮箱绑定到当前 Telegram 用户 |
| `POST` | `/telegram/unbind_address` | TG initData | `telegram_api/index.ts:76` | 解绑当前 Telegram 用户的指定邮箱 |
| `POST` | `/telegram/get_mail` | TG initData | `telegram_api/index.ts:77` | 按 `mailId` 取邮件；管理员可读任意邮件，普通用户只能读已绑定邮箱 |

## 兑换码（3）

未启用 `ENABLE_REDEEM_CODE` 时这一组接口返回 404（`redeem_api/index.ts:9` 的中间件），并受站点密码与限流约束。

| 方法 | 路径 | 鉴权 | 源码 | 说明 |
| --- | --- | --- | --- | --- |
| `POST` | `/redeem_api/query` | 无 | `redeem_api/index.ts:10` | 按兑换码查询类型、面值与状态（`unused`/`redeemed`/`expired`） |
| `POST` | `/redeem_api/result` | 无 | `redeem_api/index.ts:11` | 查询已兑换兑换码的结果（角色、发信额度或专属邮箱） |
| `POST` | `/redeem_api/redeem` | 无 | `redeem_api/index.ts:12` | 兑换权益：角色、发信额度或专属邮箱；并发冲突返回 409 |

## 根路径（2）

| 方法 | 路径 | 鉴权 | 源码 | 说明 |
| --- | --- | --- | --- | --- |
| `GET` | `/` | 无 | `worker.ts:314` | 健康检查：确认 `DB`、`JWT_SECRET`、`DOMAINS` 已配置，成功返回 `OK` |
| `GET` | `/health_check` | 无 | `worker.ts:315` | 与 `/` 相同的健康检查，供探活使用 |

## 附注

### 鉴权例外与叠加规则

- `/api/new_address` 不走地址 JWT：`worker.ts:159` 只尝试解析可选的 `x-user-token`，用于识别登录用户与地址数量上限。
- `/api/address_login` 跳过地址 JWT（`worker.ts:170`），否则无法用密码换取 JWT。
- `x-user-access-token` 是可选凭据：`checkoutUserRolePayload`（`worker.ts:135-155`）在没有该头时直接放行，提供时校验过期时间。两类调用点校验粒度不同：`/api/settings`、`/api/send_mail` 的调用点（`worker.ts:167`）**不传 `user_id`**，只校验过期时间；`/user_api/bind_address*`、`/user_api/address/` 前缀的调用点（`worker.ts:224`）传入 `user_id`，额外校验令牌归属。`/user_api/unbind_address`、`/user_api/transfer_address` 不校验角色令牌。
- `POST /user_api/bind_address` 需要双凭据：用户 JWT 用 `x-user-token`，地址 JWT 仍放在 `Authorization` 头（`worker.ts:227`）。
- `/admin/*` 支持三种放行方式：`x-admin-auth` 命中 `ADMIN_PASSWORDS`；`x-user-access-token` 的角色等于 `ADMIN_USER_ROLE`；配置 `DISABLE_ADMIN_PASSWORD_CHECK` 后直接放行。配置 `ADMIN_API_IP_WHITELIST` 时，来源 IP 不在列表一律 403。
- `/telegram/webhook` 不需要站点密码，但需要配置 `TELEGRAM_BOT_TOKEN` 与 `KV`。该接口**本身不校验请求来源**：handler（`telegram_api/index.ts:35-48`）直接解析请求体并交给 Telegraf，`setWebhook`（`telegram_api/index.ts:56`）也未传 `secret_token`，全仓没有 `X-Telegram-Bot-Api-Secret-Token` 校验，因此仅依赖 Webhook URL 保密；如需来源校验，应配置 `secret_token` 并校验 `X-Telegram-Bot-Api-Secret-Token` 请求头。

### 能力开关对接口可见性的影响

`GET /open_api/settings` 返回的开关决定前端是否展示对应入口，服务端则以环境变量为准：

| 环境变量 | 影响的接口 | 未启用时 |
| --- | --- | --- |
| `PASSWORDS` | 除 `/open_api/*`、`/telegram/*` 外的全部接口 | 缺少 `x-custom-auth` 返回 401 |
| `ENABLE_USER_CREATE_EMAIL` | `POST /api/new_address` | 403 |
| `DISABLE_ANONYMOUS_USER_CREATE_EMAIL` | `POST /api/new_address` | 匿名调用 403 |
| `DISABLE_CUSTOM_ADDRESS_NAME` | `POST /api/new_address` | 忽略自定义名称，随机生成 |
| `ENABLE_USER_DELETE_EMAIL` | 6 个删除类接口（`DELETE /api/mails/:id`、`/api/clear_inbox`、`/api/clear_sent_items`、`/api/sendbox/:id`、`/user_api/mails/:id`、`/user_api/sendbox/:mail_id`） | 403 |
| `ENABLE_USER_DELETE_EMAIL`（删除地址） | `DELETE /api/delete_address` | 500：`common.ts:631-632` 直接 throw，`mails_crud.ts:76` 未捕获，由全局 `onError` 转 500 |
| `ENABLE_MAIL_READ_STATUS` | `PATCH /api/mails/:id/read` | 403 |
| `ENABLE_AUTO_REPLY` | `/api/auto_reply` | 403 |
| `ENABLE_ADDRESS_PASSWORD` | `/api/address_change_password`、`/api/address_login`、`/admin/address/:id/reset_password` | 403 |
| `ENABLE_WEBHOOK` + `KV` | `/api/webhook/*`、`/admin/webhook/*`、`/admin/mail_webhook/*` | 400（缺 `KV`）或 403（未启用 Webhook） |
| `ENABLE_WEBHOOK` | `/open_api/a/...`（Webhook 附件下载） | 403（`open_api/webhook_attachment.ts:17-19`） |
| S3 变量 | `/api/attachment/*` | 请求失败（S3 配置缺失） |
| `SEND_MAIL` 绑定 / Resend / SMTP | `/api/send_mail`、`/external/api/send_mail`、`/user_api/address/:address_id/send_mail`、`/admin/send_mail*` | 发信失败返回 400 |
| `DISABLE_USER_SYSTEM` | 全部 `/user_api/*` | 403 |
| `ENABLE_REDEEM_CODE` | `/redeem_api/*`、`/admin/redeem_codes*` | 404 |
| `TELEGRAM_BOT_TOKEN` + `KV` | `/telegram/*`、`/admin/telegram/*` | 400 |
| `ADMIN_API_IP_WHITELIST` | 全部 `/admin/*` | 来源 IP 不在列表返回 403 |
| `DISABLE_ADMIN_PASSWORD_CHECK` | 全部 `/admin/*` | 关闭管理员密码与角色校验 |
| `RATE_LIMITER` + IP 黑名单 | 限流名单内的接口 | 429 或 403 |
| `DB`、`JWT_SECRET` | 除静态资源外的全部请求 | 400 |
| `DOMAINS` | `GET /`、`GET /health_check` | 400 |

### 已知源码差异

- `worker/src/admin_api/index.ts:97-99` 的 3 条数据库路由注册时**没有前导 `/`**（写作 `'admin/db_version'`），而其他路由都带前导 `/`。调用方（前端 `DatabaseManager.vue`）仍按 `/admin/db_version`、`/admin/db_initialize`、`/admin/db_migration` 访问，本页按实际调用路径记录；该差异仅在源码层面确认，但已在部署实例上带管理员凭据实测 `GET /admin/db_version` 返回 200（`current_db_version` 为 `v0.0.9`），说明调用路径可达，不是 404。
- `worker.ts:43-50` 的静态资源中间件在绑定 `ASSETS` 时，会把所有非 API 前缀路径（包括 `/`、`/health_check`）交给静态资源处理，此时健康检查接口不会被命中。未绑定 `ASSETS` 时按上表行为工作。
- 除本页列出的路由外，`worker/src` 中没有其他 `get`/`post`/`put`/`delete`/`patch` 注册；`api.use(...)`、`app.use(...)` 均为中间件，不计入接口。
