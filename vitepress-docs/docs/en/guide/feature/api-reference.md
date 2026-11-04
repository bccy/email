# API Reference

This page is generated from the `worker/src` source and covers all **133** HTTP endpoints exposed by the Worker: the routes registered by the 8 `app.route('/', ...)` modules in `worker.ts`, plus the `/` and `/health_check` routes mounted directly in `worker.ts`. The trailing `app.all('/*')` is only a 404 fallback and is not counted as an endpoint.

- The "Source" column is relative to `worker/src/`, and the line number is the route registration.
- The "Auth" column lists only the endpoint's **own** authentication; the site password requirement for all paths is described below.

## Overview

### Base URL

All endpoints live under the Worker domain, for example `https://your-worker.example.com`.

- The frontend is same-origin by default: `pages/functions/_middleware.js` forwards requests prefixed with `/api/`, `/open_api/`, `/user_api/`, `/admin/`, `/telegram/`, `/external/` and `/redeem_api/` to the Worker.
- The frontend may point at a separate API domain with `VITE_API_BASE`; when empty it uses the same origin.
- Paths below are complete paths (prefix included), and `<...>` marks a path parameter.

### Authentication

| Method | Location | Description |
| --- | --- | --- |
| Address JWT | `Authorization: Bearer <address JWT>` | The `jwt` returned when creating a mailbox; represents one address. Used by `/api/*` by default |
| User JWT | `x-user-token: <user JWT>` | Returned by `/user_api/login`, `/user_api/register`, etc.; represents a user account |
| User role token | `x-user-access-token: <access token>` | Optional credential: returned by `/user_api/settings`, valid for 1 hour and carries `user_role`. Requests without it are allowed through; when provided, its expiry and `user_id` are checked (`worker.ts:135-155`) |
| Admin password | `x-admin-auth: <one of ADMIN_PASSWORDS>` | `/admin/*`; when `ADMIN_USER_ROLE` is set, an `x-user-access-token` with that role also works |
| Site password | `x-custom-auth: <one of PASSWORDS>` | When `PASSWORDS` is set, required for every request except `/open_api/*` and `/telegram/*` |
| Language | `x-lang: zh` / `en` | Selects the error message language; defaults to `DEFAULT_LANG` |
| Telegram initData | request body `initData` field | `/telegram/*` mini-app endpoints, verified with an HMAC keyed by the bot token |
| Body token | request body `token` field | `/external/api/send_mail` only, for clients that cannot set headers |
| Signed URL | `:expires`, `:signature` path segments | `/open_api/a/...` only; HMAC signature plus expiry |

::: tip Address JWT and user JWT are different credentials
An address JWT can only access its own mailbox (`/api/*`), and a user JWT can only access the user account (`/user_api/*`). They are not interchangeable; see [New Address API](./new-address-api.md).
:::

### Conventions

- **Pagination**: list endpoints read `limit` and `offset`; `limit` must be 1–100 and `offset` must be ≥ 0, otherwise 400 is returned. Responses are `{ results, count }`, where `count` is computed only when `offset=0` and is 0 otherwise (`handleListQuery` at `worker/src/common.ts:678-714`, `hideObjectFields` at `716-725`, `handleMailListQuery` at `730-753`).
- **Error text**: most errors are returned as plain text via `c.text(...)`, localized by `x-lang`. Some auth errors return `{ code, message }` JSON. Uncaught exceptions are handled by the global `onError` and return `{ code: "INTERNAL_SERVER_ERROR", message }` with status 500.
- **Rate limiting and access control**: `/api/new_address`, `/api/send_mail`, `/external/api/send_mail`, `/user_api/address/:address_id/send_mail`, `/user_api/register`, `/user_api/verify_code` and `/redeem_api/*` first pass through the `RATE_LIMITER` (429 when exceeded) and the IP blacklist / daily limit checks.

### Error codes

`worker/src/error_codes.ts` defines 4 JSON error codes:

| code | When it is returned |
| --- | --- |
| `INTERNAL_SERVER_ERROR` | Uncaught exception, status 500 |
| `AUTH_SITE_PASSWORD_INVALID` | Site password missing or wrong |
| `AUTH_ADMIN_CREDENTIAL_INVALID` | Invalid admin credentials, or the user role is not the admin role |
| `AUTH_USER_ACCESS_TOKEN_EXPIRED` | `x-user-access-token` has expired |

Common HTTP status codes:

| Status | Meaning | Typical response |
| --- | --- | --- |
| 400 | Invalid/missing parameters, or unconfigured environment variables | `DBNotAvailableMsg`, `JWTSecretNotSetMsg`, `DomainsNotSetMsg`, `InvalidLimitMsg` |
| 401 | Authentication failed | `AUTH_*` JSON, or `InvalidAddressCredentialMsg`, `UserTokenExpiredMsg` |
| 403 | Feature disabled or no permission | `ENABLE_*` off, IP whitelist, webhook allow list |
| 404 | Unknown route, or redeem codes disabled | Hono's default `404 Not Found` (`c.notFound()`, e.g. when redeem codes are disabled) versus the fallback `Not Found` (`app.all('/*')`, `worker.ts:316`) |
| 409 | Concurrent redemption conflict, or the user already holds another role | `RedeemCodeUnavailableMsg`, `RedeemRoleConflictMsg` (`redeem_code.ts:226`) |
| 429 | Rate limited | `IP=<ip> Rate limit exceeded for <path>` |
| 500 | Server error | `{ code: "INTERNAL_SERVER_ERROR", message }` |

## Endpoint count

| Module | Endpoints |
| --- | --- |
| Public / Open API | 5 |
| Mailbox API | 23 |
| Send Mail API | 5 |
| User API | 26 |
| Admin API | 59 |
| Telegram | 10 |
| Redeem codes | 3 |
| Root | 2 |
| **Total** | **133** |

## Public / Open API (5)

No session credentials are required and the group is exempt from the site password; `/open_api/a/...` relies on a signed URL instead.

| Method | Path | Auth | Source | Description |
| --- | --- | --- | --- | --- |
| `GET` | `/open_api/settings` | None | `commom_api.ts:11` | Public bootstrap config for the frontend: title, announcement, domains, feature flags, SMTP/IMAP proxy and version; `needAuth` reports whether a site password is enabled |
| `GET` | `/open_api/a/:mail_id/:index/:expires/:signature` | Signed URL | `commom_api.ts:79` | Downloads attachment `index` of a mail using a webhook attachment signature; verifies the HMAC and expiry and requires `ENABLE_WEBHOOK` |
| `POST` | `/open_api/site_login` | None | `open_api/auth.ts:10` | Verifies the site password (`PASSWORDS`, optionally with Turnstile) and returns `{ success: true }` |
| `POST` | `/open_api/admin_login` | None | `open_api/auth.ts:28` | Verifies an admin password (`ADMIN_PASSWORDS`) and returns `{ success: true }` |
| `POST` | `/open_api/credential_login` | None | `open_api/auth.ts:46` | Verifies an address JWT and confirms the address still exists, returning `{ success: true }` |

## Mailbox API (23)

Address-JWT based; `/api/*` is authenticated by the middleware at `worker.ts:158`. The "Auth" column marks the exceptions.

| Method | Path | Auth | Source | Description |
| --- | --- | --- | --- | --- |
| `GET` | `/api/auto_reply` | Address JWT | `mails_api/index.ts:14` | Reads the auto-reply settings of the current address (subject, message, enabled, prefix, name); returns `{}` when unset; requires `ENABLE_AUTO_REPLY` |
| `POST` | `/api/auto_reply` | Address JWT | `mails_api/index.ts:15` | Saves auto-reply settings; subject and message are required when enabled and both are limited to 255 characters; requires `ENABLE_AUTO_REPLY` |
| `GET` | `/api/webhook/settings` | Address JWT | `mails_api/index.ts:18` | Reads the current address's webhook settings; returns 403 when an admin allow list is enabled and the address is not on it |
| `POST` | `/api/webhook/settings` | Address JWT | `mails_api/index.ts:19` | Saves the current address's webhook settings after compiling and validating the filter |
| `POST` | `/api/webhook/test` | Address JWT | `mails_api/index.ts:20` | Sends a real test webhook using a random or the given `mail_id` mail |
| `POST` | `/api/webhook/check_filter` | Address JWT | `mails_api/index.ts:21` | Checks whether the filter matches a random or the given mail and returns `matched` |
| `GET` | `/api/attachment/list` | Address JWT | `mails_api/index.ts:24` | Lists S3 attachment keys under the current address prefix; requires S3 variables |
| `POST` | `/api/attachment/delete` | Address JWT | `mails_api/index.ts:25` | Deletes an attachment key of the current address from S3 |
| `POST` | `/api/attachment/put_url` | Address JWT | `mails_api/index.ts:26` | Creates a presigned PUT URL for the current address |
| `POST` | `/api/attachment/get_url` | Address JWT | `mails_api/index.ts:27` | Creates a presigned GET URL for the current address |
| `GET` | `/api/mails` | Address JWT | `mails_api/index.ts:30` | Paginates the current address's inbox (`raw_mails`) |
| `GET` | `/api/mail/:mail_id` | Address JWT | `mails_api/index.ts:31` | Returns the raw content of one mail of the current address, or `null` when missing |
| `DELETE` | `/api/mails/:id` | Address JWT | `mails_api/index.ts:32` | Deletes one mail of the current address; requires `ENABLE_USER_DELETE_EMAIL` |
| `PATCH` | `/api/mails/:id/read` | Address JWT | `mails_api/index.ts:33` | Sets the read status of a mail (body `isUnread`); requires `ENABLE_MAIL_READ_STATUS` |
| `GET` | `/api/parsed_mails` | Address JWT | `mails_api/index.ts:36` | Paginates the inbox and parses sender, subject, text, html and attachment metadata server-side |
| `GET` | `/api/parsed_mail/:mail_id` | Address JWT | `mails_api/index.ts:37` | Server-side parsed result of a single mail |
| `GET` | `/api/settings` | Address JWT (optional role token) | `mails_api/index.ts:40` | Returns the current address and send balance `{ address, send_balance }` and refreshes the address activity time |
| `POST` | `/api/new_address` | Optional user JWT | `mails_api/index.ts:41` | Creates a mailbox and returns `{ jwt, address, address_id }`; governed by the creation switches, Turnstile, address block list and rate limiting |
| `DELETE` | `/api/delete_address` | Address JWT | `mails_api/index.ts:42` | Deletes the current address together with its mails, sent items and bindings; when `ENABLE_USER_DELETE_EMAIL` is off it throws and the global `onError` returns 500 |
| `DELETE` | `/api/clear_inbox` | Address JWT | `mails_api/index.ts:43` | Clears the current address's inbox; requires `ENABLE_USER_DELETE_EMAIL` |
| `DELETE` | `/api/clear_sent_items` | Address JWT | `mails_api/index.ts:44` | Clears the current address's sent items; requires `ENABLE_USER_DELETE_EMAIL` |
| `POST` | `/api/address_change_password` | Address JWT | `mails_api/index.ts:47` | Changes the address password (stores the frontend SHA-256 hash as-is); requires `ENABLE_ADDRESS_PASSWORD` |
| `POST` | `/api/address_login` | None (address JWT exempt) | `mails_api/index.ts:48` | Exchanges mailbox name + password for an address JWT; requires `ENABLE_ADDRESS_PASSWORD` |

## Send Mail API (5)

The transport is chosen by the `SEND_MAIL` binding, Resend or SMTP, and sending is bounded by balance and limits.

| Method | Path | Auth | Source | Description |
| --- | --- | --- | --- | --- |
| `POST` | `/api/request_send_mail_access` | Address JWT | `mails_api/send_mail_api.ts:18` | Requests send access for the current address and writes a pending record; a duplicate request returns 400 |
| `POST` | `/api/send_mail` | Address JWT (optional role token) | `mails_api/send_mail_api.ts:251` | Sends a mail from the current address and stores it in the sendbox; failures return 400 |
| `POST` | `/external/api/send_mail` | Body `token` | `mails_api/send_mail_api.ts:263` | External integration: the address JWT is passed in the body `token` field instead of a header |
| `GET` | `/api/sendbox` | Address JWT | `mails_api/send_mail_api.ts:291` | Paginates the current address's sent items |
| `DELETE` | `/api/sendbox/:id` | Address JWT | `mails_api/send_mail_api.ts:297` | Deletes one sent item of the current address; requires `ENABLE_USER_DELETE_EMAIL` |

## User API (26)

User-JWT based; `/user_api/*` is authenticated by the middleware at `worker.ts:185`. When `DISABLE_USER_SYSTEM` is on, the whole group returns 403.

| Method | Path | Auth | Source | Description |
| --- | --- | --- | --- | --- |
| `GET` | `/user_api/open_settings` | None | `user_api/index.ts:14` | Public user-system config: enabled flag, mail verification requirement and OAuth2 client list |
| `GET` | `/user_api/settings` | User JWT | `user_api/index.ts:15` | Returns user info, role, admin flag, a 1-hour `access_token`, and a fresh `new_user_token` when the current one nears expiry |
| `GET` | `/user_api/mails` | User JWT | `user_api/index.ts:18` | Paginates the inbox across all mailboxes bound to the user, filterable by `address` |
| `DELETE` | `/user_api/mails/:id` | User JWT | `user_api/index.ts:19` | Deletes one mail in the user's bound mailboxes; requires `ENABLE_USER_DELETE_EMAIL` |
| `GET` | `/user_api/address/:address_id/settings` | User JWT (optional role token) | `user_api/index.ts:22` | Returns the bound address and its send balance |
| `POST` | `/user_api/address/:address_id/request_send_mail_access` | User JWT (optional role token) | `user_api/index.ts:23` | Requests send access for a bound mailbox |
| `POST` | `/user_api/address/:address_id/send_mail` | User JWT (optional role token) | `user_api/index.ts:24` | Sends a mail from a bound mailbox and stores it in the sendbox |
| `GET` | `/user_api/sendbox` | User JWT | `user_api/index.ts:25` | Paginates sent items across the user's bound mailboxes, filterable by `address` |
| `DELETE` | `/user_api/sendbox/:mail_id` | User JWT | `user_api/index.ts:26` | Deletes one sent item of the user's bound mailboxes; requires `ENABLE_USER_DELETE_EMAIL` |
| `POST` | `/user_api/login` | None | `user_api/index.ts:29` | Email + password login returning a 30-day user JWT |
| `POST` | `/user_api/verify_code` | None | `user_api/index.ts:30` | Sends a 6-digit verification code to the registration email (stored in KV for 5 minutes); constrained by Turnstile and the mail domain allow list |
| `POST` | `/user_api/register` | None | `user_api/index.ts:31` | Registers a user with email, password and verification code; the user system must be enabled |
| `GET` | `/user_api/oauth2/login_url` | None | `user_api/index.ts:34` | Builds the third-party OAuth2 authorization URL for a `clientID` |
| `POST` | `/user_api/oauth2/callback` | None | `user_api/index.ts:35` | Exchanges the `code` for an access token, fetches the user profile and logs in or registers |
| `GET` | `/user_api/bind_address` | User JWT (optional role token) | `user_api/index.ts:38` | Paginates the user's bound mailboxes with mail and send counts, filterable by `query` |
| `POST` | `/user_api/bind_address` | User JWT (optional role token) + address JWT | `user_api/index.ts:39` | Binds the mailbox identified by the address JWT to the current user, enforcing the address count limit |
| `GET` | `/user_api/bind_address_jwt/:address_id` | User JWT (optional role token) | `user_api/index.ts:40` | Issues an address JWT for a bound mailbox |
| `POST` | `/user_api/unbind_address` | User JWT | `user_api/index.ts:41` | Unbinds a mailbox from the current user |
| `POST` | `/user_api/transfer_address` | User JWT | `user_api/index.ts:42` | Transfers a mailbox to another user by recreating the address row and moving the binding |
| `GET` | `/user_api/passkey` | User JWT | `user_api/index.ts:45` | Lists the user's passkeys |
| `POST` | `/user_api/passkey/rename` | User JWT | `user_api/index.ts:46` | Renames a passkey; the name is limited to 255 characters |
| `DELETE` | `/user_api/passkey/:passkey_id` | User JWT | `user_api/index.ts:47` | Deletes one of the user's passkeys |
| `POST` | `/user_api/passkey/register_request` | User JWT | `user_api/index.ts:48` | Creates a passkey registration challenge (WebAuthn options) |
| `POST` | `/user_api/passkey/register_response` | User JWT | `user_api/index.ts:49` | Verifies and stores the passkey registration result |
| `POST` | `/user_api/passkey/authenticate_request` | None | `user_api/index.ts:50` | Creates a passkey login challenge |
| `POST` | `/user_api/passkey/authenticate_response` | None | `user_api/index.ts:51` | Verifies the passkey assertion and returns a user JWT |

## Admin API (59)

`/admin/*` is authenticated by the middleware at `worker.ts:235`: either `x-admin-auth` matching `ADMIN_PASSWORDS`, or an `x-user-access-token` whose role equals `ADMIN_USER_ROLE`. When `ADMIN_API_IP_WHITELIST` is set, the source IP is checked as well.

### Mailboxes

| Method | Path | Auth | Source | Description |
| --- | --- | --- | --- | --- |
| `GET` | `/admin/address` | Admin | `admin_api/index.ts:26` | Paginates all mailboxes with keyword search, sorting and mail/send counts; passwords are hidden |
| `POST` | `/admin/new_address` | Admin | `admin_api/index.ts:27` | Admin mailbox creation (skips domain allow list and length checks); returns an address JWT |
| `DELETE` | `/admin/delete_address/:id` | Admin | `admin_api/index.ts:28` | Deletes an address and cascades mails, sent items, send access, auto-reply and user bindings in one transaction |
| `DELETE` | `/admin/clear_inbox/:id` | Admin | `admin_api/index.ts:29` | Clears the inbox of the given address |
| `DELETE` | `/admin/clear_sent_items/:id` | Admin | `admin_api/index.ts:30` | Clears the sent items of the given address |
| `GET` | `/admin/show_password/:id` | Admin | `admin_api/index.ts:31` | Issues an address JWT for the given address (console "show password") |
| `POST` | `/admin/address/:id/reset_password` | Admin | `admin_api/index.ts:32` | Resets the address password (stores the frontend SHA-256 hash); requires `ENABLE_ADDRESS_PASSWORD` |

### Mails

| Method | Path | Auth | Source | Description |
| --- | --- | --- | --- | --- |
| `GET` | `/admin/mails` | Admin | `admin_api/index.ts:35` | Paginates all mails, filterable by `address` |
| `GET` | `/admin/mails_unknow` | Admin | `admin_api/index.ts:36` | Paginates "unknown mails" whose address does not exist |
| `GET` | `/admin/mails/:id` | Admin | `admin_api/index.ts:37` | Reads any mail by ID |
| `DELETE` | `/admin/mails/:id` | Admin | `admin_api/index.ts:38` | Deletes any mail by ID |

### Send access and sendbox

| Method | Path | Auth | Source | Description |
| --- | --- | --- | --- | --- |
| `GET` | `/admin/address_sender` | Admin | `admin_api/index.ts:41` | Paginates address send-access and balance records, filterable by `address` |
| `POST` | `/admin/address_sender` | Admin | `admin_api/index.ts:42` | Updates send enablement and balance for an address and sends it an internal notification mail |
| `DELETE` | `/admin/address_sender/:id` | Admin | `admin_api/index.ts:43` | Deletes a send-access record |
| `GET` | `/admin/sendbox` | Admin | `admin_api/index.ts:46` | Paginates all sent items, filterable by `address` |
| `DELETE` | `/admin/sendbox/:id` | Admin | `admin_api/index.ts:47` | Deletes one sent item |

### Statistics and global lists

| Method | Path | Auth | Source | Description |
| --- | --- | --- | --- | --- |
| `GET` | `/admin/statistics` | Admin | `admin_api/index.ts:50` | Returns mail, address, 7/30-day active address, user and send totals |
| `GET` | `/admin/account_settings` | Admin | `admin_api/index.ts:53` | Reads address/send/sender block lists, verified addresses, mail rules and send limit config |
| `POST` | `/admin/account_settings` | Admin | `admin_api/index.ts:54` | Saves the global lists and rules above |
| `POST` | `/admin/cleanup` | Admin | `admin_api/index.ts:57` | Runs a manual cleanup by `cleanType` and `cleanDays` |
| `GET` | `/admin/auto_cleanup` | Admin | `admin_api/index.ts:58` | Reads the auto-cleanup configuration |
| `POST` | `/admin/auto_cleanup` | Admin | `admin_api/index.ts:59` | Saves the auto-cleanup configuration and validates custom SQL cleanup statements |

### User management

| Method | Path | Auth | Source | Description |
| --- | --- | --- | --- | --- |
| `GET` | `/admin/user_settings` | Admin | `admin_api/index.ts:62` | Reads user-system settings: enabled, mail verification, max address count, etc. |
| `POST` | `/admin/user_settings` | Admin | `admin_api/index.ts:63` | Saves user-system settings and validates the verify-mail sender domain and address limit |
| `GET` | `/admin/users` | Admin | `admin_api/index.ts:64` | Paginates users with email search, including role and bound address count |
| `DELETE` | `/admin/users/:user_id` | Admin | `admin_api/index.ts:65` | Deletes a user and its address bindings |
| `POST` | `/admin/users` | Admin | `admin_api/index.ts:66` | Admin user creation (email + password) |
| `POST` | `/admin/users/:user_id/reset_password` | Admin | `admin_api/index.ts:67` | Resets a user's password |
| `GET` | `/admin/user_roles` | Admin | `admin_api/index.ts:68` | Returns the roles configured in `USER_ROLES` |
| `POST` | `/admin/user_roles` | Admin | `admin_api/index.ts:69` | Sets or clears a user's role |
| `GET` | `/admin/role_address_config` | Admin | `admin_api/index.ts:70` | Reads the per-role address count limits |
| `POST` | `/admin/role_address_config` | Admin | `admin_api/index.ts:71` | Saves the per-role address count limits |
| `GET` | `/admin/users/bind_address/:user_id` | Admin | `admin_api/index.ts:72` | Lists the mailboxes bound to a user |
| `POST` | `/admin/users/bind_address` | Admin | `admin_api/index.ts:73` | Binds a mailbox to a user by `user_email`/`address` or by IDs |

### OAuth2, webhooks and worker config

| Method | Path | Auth | Source | Description |
| --- | --- | --- | --- | --- |
| `GET` | `/admin/user_oauth2_settings` | Admin | `admin_api/index.ts:76` | Reads the OAuth2 provider configuration list |
| `POST` | `/admin/user_oauth2_settings` | Admin | `admin_api/index.ts:77` | Saves OAuth2 providers and validates required fields per entry |
| `GET` | `/admin/webhook/settings` | Admin | `admin_api/index.ts:80` | Reads the global webhook allow list settings |
| `POST` | `/admin/webhook/settings` | Admin | `admin_api/index.ts:81` | Saves the global webhook allow list settings |
| `GET` | `/admin/mail_webhook/settings` | Admin | `admin_api/index.ts:84` | Reads the global mail webhook settings |
| `POST` | `/admin/mail_webhook/settings` | Admin | `admin_api/index.ts:85` | Saves the global mail webhook settings after validating the filter |
| `POST` | `/admin/mail_webhook/test` | Admin | `admin_api/index.ts:86` | Sends a test request to the global webhook with a random or the given mail |
| `POST` | `/admin/mail_webhook/check_filter` | Admin | `admin_api/index.ts:87` | Checks whether the global webhook filter matches |
| `GET` | `/admin/worker/configs` | Admin | `admin_api/index.ts:90` | Returns a snapshot of Worker environment configuration; passwords and secrets are exposed only as counts or booleans |

### Sending, database and generic config

| Method | Path | Auth | Source | Description |
| --- | --- | --- | --- | --- |
| `POST` | `/admin/send_mail` | Admin | `admin_api/index.ts:93` | Admin send from any `from_mail`, skipping balance and address-ownership checks while still validating the sender domain, send block list and transport |
| `POST` | `/admin/send_mail_by_binding` | Admin | `admin_api/index.ts:94` | Sends a raw mail through the `SEND_MAIL` binding after checking that binding send is enabled for the sender domain; returns 400 when the binding is missing |
| `GET` | `/admin/db_version` | Admin | `admin_api/index.ts:97` | Returns current/code DB version, initialization and migration flags, and database size |
| `POST` | `/admin/db_initialize` | Admin | `admin_api/index.ts:98` | Executes the schema SQL and records the DB version |
| `POST` | `/admin/db_migration` | Admin | `admin_api/index.ts:99` | Applies incremental migrations in version order |
| `GET` | `/admin/config/:key` | Admin | `admin_api/index.ts:102` | Reads one generic admin config entry; the key must match `[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}` |
| `POST` | `/admin/config` | Admin | `admin_api/index.ts:103` | Saves one generic admin config entry; `value` must be a string |

### Redeem code administration

This group returns 404 unless `ENABLE_REDEEM_CODE` is enabled.

| Method | Path | Auth | Source | Description |
| --- | --- | --- | --- | --- |
| `GET` | `/admin/redeem_codes` | Admin | `admin_api/index.ts:108` | Paginates redeem codes by `redeem_type` with code search; result fields are decrypted |
| `GET` | `/admin/redeem_codes/export` | Admin | `admin_api/index.ts:109` | Exports redeem codes of one type as CSV with business columns; `limit` is capped |
| `POST` | `/admin/redeem_codes/batch` | Admin | `admin_api/index.ts:110` | Generates a batch of redeem codes (UUID v4) and returns the generated codes |
| `PUT` | `/admin/redeem_codes/:id` | Admin | `admin_api/index.ts:111` | Updates a redeem code's type, value, enabled flag or expiry |
| `DELETE` | `/admin/redeem_codes/:id` | Admin | `admin_api/index.ts:112` | Deletes a redeem code |

### IP blacklist and AI extraction

| Method | Path | Auth | Source | Description |
| --- | --- | --- | --- | --- |
| `GET` | `/admin/ip_blacklist/settings` | Admin | `admin_api/index.ts:115` | Reads IP, ASN and fingerprint blacklists, the whitelist and daily limit settings |
| `POST` | `/admin/ip_blacklist/settings` | Admin | `admin_api/index.ts:116` | Saves the IP blacklist settings with per-field validation |
| `GET` | `/admin/ai_extract/settings` | Admin | `admin_api/index.ts:119` | Reads the AI mail extraction allow list settings |
| `POST` | `/admin/ai_extract/settings` | Admin | `admin_api/index.ts:120` | Saves the AI mail extraction allow list settings |

## Telegram (10)

`/telegram/*` is exempt from the site password by the global middleware, but `telegram_api/index.ts:13` requires `TELEGRAM_BOT_TOKEN` and `KV` and returns 400 otherwise; `/admin/telegram/*` additionally requires admin authentication.

| Method | Path | Auth | Source | Description |
| --- | --- | --- | --- | --- |
| `POST` | `/telegram/webhook` | None (relies on URL secrecy, see Notes) | `telegram_api/index.ts:35` | Telegram bot webhook entry that hands the update to Telegraf |
| `POST` | `/admin/telegram/init` | Admin | `telegram_api/index.ts:50` | Registers `/telegram/webhook` on the current domain as the bot webhook and initializes commands |
| `GET` | `/admin/telegram/status` | Admin | `telegram_api/index.ts:63` | Returns the bot's webhook info and registered commands |
| `GET` | `/admin/telegram/settings` | Admin | `telegram_api/index.ts:71` | Reads Telegram settings: allow list, mini-app URL and global push list |
| `POST` | `/admin/telegram/settings` | Admin | `telegram_api/index.ts:72` | Saves Telegram settings |
| `POST` | `/telegram/get_bind_address` | TG initData | `telegram_api/index.ts:73` | Returns the mailboxes bound to the current Telegram user, with their address JWTs |
| `POST` | `/telegram/new_address` | TG initData | `telegram_api/index.ts:74` | Creates and binds a new mailbox for the current Telegram user |
| `POST` | `/telegram/bind_address` | TG initData | `telegram_api/index.ts:75` | Binds a mailbox to the current Telegram user using an address JWT |
| `POST` | `/telegram/unbind_address` | TG initData | `telegram_api/index.ts:76` | Unbinds a mailbox from the current Telegram user |
| `POST` | `/telegram/get_mail` | TG initData | `telegram_api/index.ts:77` | Returns a mail by `mailId`; admins may read any mail, regular users only their bound mailboxes |

## Redeem codes (3)

This group returns 404 unless `ENABLE_REDEEM_CODE` is enabled (middleware at `redeem_api/index.ts:9`), and is subject to the site password and rate limiting.

| Method | Path | Auth | Source | Description |
| --- | --- | --- | --- | --- |
| `POST` | `/redeem_api/query` | None | `redeem_api/index.ts:10` | Looks up a redeem code's type, value and status (`unused`/`redeemed`/`expired`) |
| `POST` | `/redeem_api/result` | None | `redeem_api/index.ts:11` | Looks up the result of a redeemed code (role, send balance or dedicated mailbox) |
| `POST` | `/redeem_api/redeem` | None | `redeem_api/index.ts:12` | Redeems a code for a role, send balance or dedicated mailbox; a concurrent conflict returns 409 |

## Root (2)

| Method | Path | Auth | Source | Description |
| --- | --- | --- | --- | --- |
| `GET` | `/` | None | `worker.ts:314` | Health check that confirms `DB`, `JWT_SECRET` and `DOMAINS` are configured and returns `OK` |
| `GET` | `/health_check` | None | `worker.ts:315` | Same health check as `/`, for liveness probes |

## Notes

### Authentication exceptions and stacking

- `/api/new_address` does not use an address JWT: `worker.ts:159` only tries to parse the optional `x-user-token` to identify a logged-in user and enforce the address count limit.
- `/api/address_login` skips the address JWT (`worker.ts:170`), otherwise exchanging a password for a JWT would be impossible.
- `x-user-access-token` is optional: `checkoutUserRolePayload` (`worker.ts:135-155`) lets the request through when the header is absent and checks expiry when it is present. The two kinds of call sites validate different scopes: `/api/settings` and `/api/send_mail` (`worker.ts:167`) call it **without `user_id`**, so only expiry is checked; the `/user_api/bind_address*` and `/user_api/address/` prefixes (`worker.ts:224`) pass `user_id` and additionally verify token ownership. `/user_api/unbind_address` and `/user_api/transfer_address` do not check the role token.
- `POST /user_api/bind_address` needs two credentials: the user JWT in `x-user-token` and the address JWT in the `Authorization` header (`worker.ts:227`).
- `/admin/*` accepts three paths: `x-admin-auth` matching `ADMIN_PASSWORDS`; an `x-user-access-token` whose role equals `ADMIN_USER_ROLE`; or a direct pass when `DISABLE_ADMIN_PASSWORD_CHECK` is set. When `ADMIN_API_IP_WHITELIST` is set, any other source IP gets 403.
- `/telegram/webhook` does not require the site password but requires `TELEGRAM_BOT_TOKEN` and `KV`. The endpoint **does not verify the request source**: the handler (`telegram_api/index.ts:35-48`) parses the body and hands it to Telegraf, and `setWebhook` (`telegram_api/index.ts:56`) passes no `secret_token`; the repository has no `X-Telegram-Bot-Api-Secret-Token` check, so it relies only on webhook URL secrecy. To verify the source, configure `secret_token` and validate that header.

### How feature switches affect endpoint visibility

The flags returned by `GET /open_api/settings` decide which entries the frontend shows; the server always follows the environment variables:

| Variable | Affected endpoints | When disabled |
| --- | --- | --- |
| `PASSWORDS` | All endpoints except `/open_api/*` and `/telegram/*` | Missing `x-custom-auth` returns 401 |
| `ENABLE_USER_CREATE_EMAIL` | `POST /api/new_address` | 403 |
| `DISABLE_ANONYMOUS_USER_CREATE_EMAIL` | `POST /api/new_address` | Anonymous calls return 403 |
| `DISABLE_CUSTOM_ADDRESS_NAME` | `POST /api/new_address` | Custom names are ignored and a random name is generated |
| `ENABLE_USER_DELETE_EMAIL` | The 6 delete endpoints (`DELETE /api/mails/:id`, `/api/clear_inbox`, `/api/clear_sent_items`, `/api/sendbox/:id`, `/user_api/mails/:id`, `/user_api/sendbox/:mail_id`) | 403 |
| `ENABLE_USER_DELETE_EMAIL` (address deletion) | `DELETE /api/delete_address` | 500: `common.ts:631-632` throws and `mails_crud.ts:76` does not catch it, so the global `onError` converts it to 500 |
| `ENABLE_MAIL_READ_STATUS` | `PATCH /api/mails/:id/read` | 403 |
| `ENABLE_AUTO_REPLY` | `/api/auto_reply` | 403 |
| `ENABLE_ADDRESS_PASSWORD` | `/api/address_change_password`, `/api/address_login`, `/admin/address/:id/reset_password` | 403 |
| `ENABLE_WEBHOOK` + `KV` | `/api/webhook/*`, `/admin/webhook/*`, `/admin/mail_webhook/*` | 400 (missing `KV`) or 403 (webhook disabled) |
| `ENABLE_WEBHOOK` | `/open_api/a/...` (webhook attachment download) | 403 (`open_api/webhook_attachment.ts:17-19`) |
| S3 variables | `/api/attachment/*` | Requests fail (S3 config missing) |
| `SEND_MAIL` binding / Resend / SMTP | `/api/send_mail`, `/external/api/send_mail`, `/user_api/address/:address_id/send_mail`, `/admin/send_mail*` | Sending fails with 400 |
| `DISABLE_USER_SYSTEM` | All `/user_api/*` | 403 |
| `ENABLE_REDEEM_CODE` | `/redeem_api/*`, `/admin/redeem_codes*` | 404 |
| `TELEGRAM_BOT_TOKEN` + `KV` | `/telegram/*`, `/admin/telegram/*` | 400 |
| `ADMIN_API_IP_WHITELIST` | All `/admin/*` | Source IP outside the list returns 403 |
| `DISABLE_ADMIN_PASSWORD_CHECK` | All `/admin/*` | Disables the admin password and role checks |
| `RATE_LIMITER` + IP blacklist | Endpoints in the rate-limit list | 429 or 403 |
| `DB`, `JWT_SECRET` | Every request except static assets | 400 |
| `DOMAINS` | `GET /`, `GET /health_check` | 400 |

### Known source discrepancies

- The 3 database routes at `worker/src/admin_api/index.ts:97-99` are registered **without a leading `/`** (`'admin/db_version'`), unlike every other route. Callers (the frontend `DatabaseManager.vue`) still use `/admin/db_version`, `/admin/db_initialize` and `/admin/db_migration`, which is what this page documents; the discrepancy is confirmed at source level, and `GET /admin/db_version` was verified on a deployed instance with admin credentials: it returns 200 with `current_db_version` = `v0.0.9`, so the path is reachable and not a 404.
- When `ASSETS` is bound, the static asset middleware at `worker.ts:43-50` serves every path outside the API prefixes (including `/` and `/health_check`) from static assets, so the health check routes are not reached. Without `ASSETS` they behave as listed above.
- Apart from the routes listed here, `worker/src` contains no other `get`/`post`/`put`/`delete`/`patch` registrations; `api.use(...)` and `app.use(...)` are middleware and are not counted as endpoints.
