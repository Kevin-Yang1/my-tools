# HUST Autologin

这个目录放两份脚本：

- `HUSTAutologin.py`: 原始版本，保留原样，主要面向手工抓包后直接复用加密 password 的用法
- `HUSTAutologin_linux.py`: Linux 服务器版，运行时动态抓 portal 页面公钥与 queryString，并按前端公开 JS 的 RSA 逻辑生成登录请求里的 `password`

## Linux 版依赖

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install requests
```

## Linux 版最小配置

必填环境变量：

- `CAMPUS_USER_ID`
- `CAMPUS_PASSWORD`

可选环境变量：

- `CAMPUS_PORTAL_ENTRY_URL`: 已知的 portal 登录页完整 URL
- `CAMPUS_QUERY_STRING`: portal URL 里的 queryString；支持原始串或已编码串
- `CAMPUS_SERVICE`: 服务名，默认空字符串
- `CAMPUS_PORTAL_INDEX_URL`: 可选；仅在你手头只有 `CAMPUS_QUERY_STRING`、同时又知道当前 portal host 时使用
- `CAMPUS_LOGIN_URL`: 显式指定登录接口；默认按 portal 域名推导
- `CAMPUS_CONNECTIVITY_TEST_URL`: 默认 `http://www.baidu.com`
- `CAMPUS_LOG_DIR`: 日志目录；默认写到当前目录下的 `logs/`

默认行为是：

- 先访问一个外网 HTTP 地址
- 如果被网络重定向到 portal 登录页，就从最终登录页 URL 中自动提取当前机器对应的 portal host 和 `queryString`
- 如果先落到一个中间跳转页，脚本会尝试从页面源码中解析真正的 `index.jsp?...` 登录页 URL 再继续
- 再按登录页公开 JS 的 RSA 逻辑生成 `password`

## 运行示例

一次性登录：

```bash
CAMPUS_USER_ID='你的学号' \
CAMPUS_PASSWORD='你的校园网密码' \
python3 scripts/hust_autologin/HUSTAutologin_linux.py --once --verbose
```

守护模式：

```bash
CAMPUS_USER_ID='你的学号' \
CAMPUS_PASSWORD='你的校园网密码' \
python3 scripts/hust_autologin/HUSTAutologin_linux.py --loop --interval 30 --startup-delay 20
```

显式指定 portal 登录页：

```bash
CAMPUS_USER_ID='你的学号' \
CAMPUS_PASSWORD='你的校园网密码' \
python3 scripts/hust_autologin/HUSTAutologin_linux.py \
  --portal-entry-url 'http://portal-host:port/eportal/index.jsp?...' \
  --once
```

## systemd 示例

环境文件，例如 `/SSD1/ykw/my-tools/scripts/hust_autologin/.env`：

```bash
CAMPUS_USER_ID=你的学号
CAMPUS_PASSWORD=你的校园网密码
```

用户级服务文件示例：

```ini
[Unit]
Description=HUST campus autologin
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/SSD1/ykw/my-tools
EnvironmentFile=/SSD1/ykw/my-tools/scripts/hust_autologin/.env
ExecStart=/usr/bin/python3 /SSD1/ykw/my-tools/scripts/hust_autologin/HUSTAutologin_linux.py --loop --interval 30 --startup-delay 20
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
```

## 说明

- Linux 版不会复用浏览器 cookie
- Linux 版不会使用原始脚本里写死的加密 password
- Linux 版默认不会写死 portal 地址，而是以每次运行时自动探测到的登录页地址为准
- Linux 版会按登录页公开 JS 的流程生成 `password`：
  1. 取明文密码
  2. 追加 `>` 和当前 queryString 里的 `mac`
  3. 反转字符串
  4. 使用 portal 页面的 RSA 公钥加密

- 如果 portal 页面结构变化，优先检查：
  - `publicKeyExponent`
  - `publicKeyModulus`
  - `passwordEncrypt`
  - 登录页最终 URL 中的 queryString

## 排障建议

- 如果你像这次一样在新机器上看到“无法从 portal 登录页 URL 中提取 queryString”，先加 `--verbose` 重跑
- DEBUG 日志现在会额外打印：
  - 当前响应链
  - 当前响应 URL
  - 页面源码里发现的 `index.jsp?...` 线索
  - 页面内容摘要
- 如果这些日志里仍然没有出现 `index.jsp?...` 或 `queryString`，说明认证前面还有一层更特殊的 JS 跳转页；这时把那一页的 HTML 保存出来，再继续补解析规则会更稳
