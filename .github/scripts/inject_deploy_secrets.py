"""把仓库 secret 里的敏感变量注入到 wrangler.toml。

背景：BACKEND_TOML 是整份 wrangler.toml 存在 Actions secret 里，wrangler 部署时
会把 [vars] 的值打印进公开的 Actions 日志（JWT_SECRET 曾因此泄露）。把敏感项
单独拆成仓库 secret 后，GitHub 会对日志里出现的值自动打码。

用法：python3 inject_deploy_secrets.py <wrangler.toml 路径>
读取环境变量 JWT_SECRET_VALUE、ADMIN_PASSWORDS_VALUE；为空则跳过该项。
对应 key 在 wrangler.toml 中不存在时返回非零退出码，避免静默没生效。
"""

import os
import re
import sys


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else "wrangler.toml"
    text = open(path, encoding="utf-8").read()
    ok = True

    jwt = os.environ.get("JWT_SECRET_VALUE", "")
    if jwt:
        raw = '"%s"' % jwt.replace("\\", "\\\\").replace('"', '\\"')
        text, hit = _set_var(text, "JWT_SECRET", raw)
        print("JWT_SECRET 注入:", "ok" if hit else "MISSING")
        ok = ok and hit

    admin = os.environ.get("ADMIN_PASSWORDS_VALUE", "")
    if admin:
        text, hit = _set_var(text, "ADMIN_PASSWORDS", admin)
        print("ADMIN_PASSWORDS 注入:", "ok" if hit else "MISSING")
        ok = ok and hit

    open(path, "w", encoding="utf-8").write(text)
    return 0 if ok else 1


def _set_var(text: str, name: str, raw: str):
    pattern = re.compile(r"(?m)^\s*%s\s*=.*$" % re.escape(name))
    if not pattern.search(text):
        return text, False
    return pattern.sub(lambda _m: "%s = %s" % (name, raw), text, count=1), True


if __name__ == "__main__":
    sys.exit(main())
