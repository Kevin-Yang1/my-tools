#!/usr/bin/env python3

"""
作用说明:
- 这是 HUST 校园网自动登录脚本的 Linux 服务器版，不修改原始 `HUSTAutologin.py`，
  而是在运行时动态抓取 portal 登录页上下文，并按前端公开 JS 的 RSA 逻辑生成登录
  请求里的 `password` 字段。
- 适合在 Linux 服务器上以一次性登录或守护模式运行，避免把抓包得到的加密 password
  长期写死在脚本里。
- 优先使用环境变量提供敏感信息，适合配合 systemd `EnvironmentFile=` 使用。

可执行示例:
- 先配置环境变量，再执行一次登录:
  `CAMPUS_USER_ID=xxxx CAMPUS_PASSWORD=xxxx python3 scripts/hust_autologin/HUSTAutologin_linux.py --once --verbose`
- 持续守护模式:
  `CAMPUS_USER_ID=xxxx CAMPUS_PASSWORD=xxxx python3 scripts/hust_autologin/HUSTAutologin_linux.py --loop --interval 30 --startup-delay 20`
- 如果已知 portal 入口 URL，可显式指定:
  `CAMPUS_USER_ID=xxxx CAMPUS_PASSWORD=xxxx python3 scripts/hust_autologin/HUSTAutologin_linux.py --portal-entry-url 'http://portal-host:port/eportal/index.jsp?...' --once`
"""

from __future__ import annotations

import html
import io
import json
import logging
import os
import random
import re
import sys
import time
from argparse import ArgumentParser
from dataclasses import dataclass
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlparse

import requests
import urllib3


try:
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer,
            encoding="utf-8",
            errors="replace",
        )
except Exception:  # noqa: BLE001
    pass

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


@dataclass
class Config:
    user_id: str
    password: str
    service: str
    portal_entry_url: str | None
    portal_index_url: str | None
    login_url: str | None
    query_string: str | None
    connectivity_test_url: str
    connectivity_timeout: int
    max_login_retries: int
    base_retry_delay: int
    retry_jitter: float
    default_interval: int
    log_dir: Path


@dataclass
class PortalContext:
    entry_url: str
    login_url: str
    query_string: str
    mac: str
    password_encrypt: str
    public_key_exponent: str
    public_key_modulus: str


def normalize_query_string(value: str) -> str | None:
    if not value:
        return None
    if "=" in value or "&" in value:
        return value
    decoded = unquote(value)
    if decoded != value and ("=" in decoded or "&" in decoded):
        return decoded
    return value


def load_config() -> Config:
    user_id = os.getenv("CAMPUS_USER_ID", "").strip()
    password = os.getenv("CAMPUS_PASSWORD", "").strip()
    service = os.getenv("CAMPUS_SERVICE", "").strip()
    portal_entry_url = os.getenv("CAMPUS_PORTAL_ENTRY_URL", "").strip() or None
    portal_index_url = os.getenv("CAMPUS_PORTAL_INDEX_URL", "").strip() or None
    login_url = os.getenv("CAMPUS_LOGIN_URL", "").strip() or None
    query_string = normalize_query_string(os.getenv("CAMPUS_QUERY_STRING", "").strip())
    connectivity_test_url = os.getenv(
        "CAMPUS_CONNECTIVITY_TEST_URL",
        "http://www.baidu.com",
    ).strip()
    connectivity_timeout = int(os.getenv("CAMPUS_CONNECTIVITY_TIMEOUT", "4"))
    max_login_retries = int(os.getenv("CAMPUS_MAX_LOGIN_RETRIES", "5"))
    base_retry_delay = int(os.getenv("CAMPUS_BASE_RETRY_DELAY", "2"))
    retry_jitter = float(os.getenv("CAMPUS_RETRY_JITTER", "0.4"))
    default_interval = int(os.getenv("CAMPUS_DEFAULT_INTERVAL", "30"))
    log_dir = Path(
        os.getenv(
            "CAMPUS_LOG_DIR",
            str(Path(__file__).resolve().parent / "logs"),
        )
    ).expanduser()
    return Config(
        user_id=user_id,
        password=password,
        service=service,
        portal_entry_url=portal_entry_url,
        portal_index_url=portal_index_url,
        login_url=login_url,
        query_string=query_string,
        connectivity_test_url=connectivity_test_url,
        connectivity_timeout=connectivity_timeout,
        max_login_retries=max_login_retries,
        base_retry_delay=base_retry_delay,
        retry_jitter=retry_jitter,
        default_interval=default_interval,
        log_dir=log_dir,
    )


CONFIG = load_config()
MAX_LOG_BYTES = 512 * 1024
BACKUP_COUNT = 3

logger = logging.getLogger("hust_autologin_linux")
logger.setLevel(logging.INFO)
_formatter = logging.Formatter(
    fmt="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger.addHandler(logging.NullHandler())


PORTAL_KEYWORDS = [
    "eportal",
    "wlanuserip",
    "portaluserv2",
    "drcom",
    "srun_portal",
]


def setup_logging(log_dir: Path) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "hust_autologin_linux.log"
    logger.handlers.clear()
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=MAX_LOG_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(_formatter)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(_formatter)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return log_file


def parse_args():
    parser = ArgumentParser(description="HUST 校园网自动登录脚本（Linux 服务器版）")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--once", action="store_true", help="只执行一次检测/登录后退出")
    mode_group.add_argument("--loop", action="store_true", help="持续守护模式（默认）")
    parser.add_argument(
        "--interval",
        type=int,
        default=CONFIG.default_interval,
        help=f"守护模式检测间隔秒数（默认 {CONFIG.default_interval}）",
    )
    parser.add_argument("--verbose", action="store_true", help="启用 DEBUG 日志输出")
    parser.add_argument(
        "--startup-delay",
        type=int,
        default=0,
        help="启动后先延迟 N 秒，再开始检测或登录",
    )
    parser.add_argument(
        "--portal-entry-url",
        default=CONFIG.portal_entry_url,
        help="显式指定 portal 登录页完整 URL；未指定时尝试自动发现",
    )
    return parser.parse_args()


def require_env_config(config: Config) -> None:
    missing: list[str] = []
    if not config.user_id:
        missing.append("CAMPUS_USER_ID")
    if not config.password:
        missing.append("CAMPUS_PASSWORD")
    if missing:
        raise SystemExit(f"缺少必填环境变量: {', '.join(missing)}")


def create_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64; rv:142.0) "
                "Gecko/20100101 Firefox/142.0"
            )
        }
    )
    return session


def looks_like_portal_url(url: str) -> bool:
    lowered = url.lower()
    return "/eportal/" in lowered or "wlanuserip=" in lowered


def response_looks_like_portal(response: requests.Response) -> bool:
    if looks_like_portal_url(response.url):
        return True
    location = response.headers.get("Location", "")
    if location and looks_like_portal_url(location):
        return True
    text = response.text.lower()
    return any(keyword in text for keyword in PORTAL_KEYWORDS)


def is_online(session: requests.Session, config: Config) -> bool:
    try:
        response = session.get(
            config.connectivity_test_url,
            timeout=config.connectivity_timeout,
            verify=False,
            allow_redirects=False,
        )
        if not (200 <= response.status_code < 400):
            return False
        if 300 <= response.status_code < 400:
            return not looks_like_portal_url(response.headers.get("Location", ""))
        return not response_looks_like_portal(response)
    except Exception:
        return False


def discover_entry_response(
    session: requests.Session,
    config: Config,
    portal_entry_url: str | None,
) -> requests.Response:
    if portal_entry_url:
        logger.debug("使用显式 portal 入口 URL: %s", portal_entry_url)
        return session.get(
            portal_entry_url,
            timeout=10,
            verify=False,
            allow_redirects=True,
        )

    if config.query_string:
        if config.portal_index_url:
            entry_url = f"{config.portal_index_url}?{config.query_string}"
            logger.debug("使用环境变量中的 queryString 构造 portal 入口 URL: %s", entry_url)
            return session.get(
                entry_url,
                timeout=10,
                verify=False,
                allow_redirects=True,
            )
        logger.debug("已提供 queryString，但未提供固定 portal 地址；先自动探测当前 portal host")

    logger.debug("尝试通过外网探测 URL 自动发现 portal 登录页")
    response = session.get(
        config.connectivity_test_url,
        timeout=10,
        verify=False,
        allow_redirects=True,
    )
    return response


def extract_hidden_input_value(html_text: str, field_name: str) -> str:
    input_pattern = re.compile(r"<input\b[^>]*>", re.IGNORECASE)
    id_pattern = re.compile(r'\b(?:id|name)\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)
    value_pattern = re.compile(r'\bvalue\s*=\s*["\']([^"\']*)["\']', re.IGNORECASE)
    for match in input_pattern.finditer(html_text):
        tag = match.group(0)
        id_match = id_pattern.search(tag)
        if not id_match:
            continue
        if id_match.group(1) != field_name:
            continue
        value_match = value_pattern.search(tag)
        if value_match:
            return html.unescape(value_match.group(1))
    return ""


def derive_login_url(entry_url: str, explicit_login_url: str | None) -> str:
    if explicit_login_url:
        return explicit_login_url
    parsed = urlparse(entry_url)
    return f"{parsed.scheme}://{parsed.netloc}/eportal/InterFace.do?method=login"


def fetch_portal_context(
    session: requests.Session,
    config: Config,
    portal_entry_url: str | None,
) -> PortalContext:
    response = discover_entry_response(session, config, portal_entry_url)
    if not response_looks_like_portal(response):
        raise RuntimeError(
            "未能定位到 portal 登录页。请确保当前网络会重定向到认证页，或显式提供 --portal-entry-url"
        )
    entry_url = response.url
    raw_query = normalize_query_string(urlparse(entry_url).query) or config.query_string
    if not raw_query:
        raise RuntimeError("无法从 portal 登录页 URL 中提取 queryString，请显式提供 CAMPUS_QUERY_STRING")

    mac = parse_qs(raw_query).get("mac", [""])[0] or "111111111"
    password_encrypt = extract_hidden_input_value(response.text, "passwordEncrypt") or "true"
    public_key_exponent = extract_hidden_input_value(response.text, "publicKeyExponent")
    public_key_modulus = extract_hidden_input_value(response.text, "publicKeyModulus")

    if password_encrypt == "true" and (not public_key_exponent or not public_key_modulus):
        raise RuntimeError("无法从 portal 登录页解析 RSA 公钥，请检查页面结构或 portal 入口 URL")

    return PortalContext(
        entry_url=entry_url,
        login_url=derive_login_url(entry_url, config.login_url),
        query_string=raw_query,
        mac=mac,
        password_encrypt=password_encrypt,
        public_key_exponent=public_key_exponent,
        public_key_modulus=public_key_modulus,
    )


def prequote_form_value(value: str) -> str:
    return quote(value, safe="")


def js_compatible_rsa_encrypt(text: str, exponent_hex: str, modulus_hex: str) -> str:
    exponent = int(exponent_hex, 16)
    modulus = int(modulus_hex, 16)
    digit_count = max(1, (modulus.bit_length() + 15) // 16)
    chunk_size = 2 * (digit_count - 1)
    if chunk_size <= 0:
        raise ValueError("无效 RSA modulus，无法计算 chunkSize")

    code_points = [ord(char) for char in text]
    while len(code_points) % chunk_size != 0:
        code_points.append(0)

    blocks: list[str] = []
    for start in range(0, len(code_points), chunk_size):
        block_value = 0
        shift = 0
        for index in range(start, start + chunk_size, 2):
            digit = code_points[index]
            digit += code_points[index + 1] << 8
            block_value |= digit << shift
            shift += 16
        crypt = pow(block_value, exponent, modulus)
        hex_text = format(crypt, "x")
        if len(hex_text) % 4 != 0:
            hex_text = hex_text.zfill(((len(hex_text) + 3) // 4) * 4)
        blocks.append(hex_text)
    return " ".join(blocks)


def build_encrypted_password(plain_password: str, context: PortalContext) -> str:
    if context.password_encrypt != "true":
        return plain_password
    password_mac = f"{plain_password}>{context.mac}"
    reversed_password_mac = password_mac[::-1]
    return js_compatible_rsa_encrypt(
        reversed_password_mac,
        context.public_key_exponent,
        context.public_key_modulus,
    )


def build_payload(config: Config, context: PortalContext) -> dict[str, str]:
    password = build_encrypted_password(config.password, context)
    return {
        "userId": prequote_form_value(config.user_id),
        "password": prequote_form_value(password),
        "service": prequote_form_value(config.service),
        "queryString": prequote_form_value(context.query_string),
        "operatorPwd": "",
        "operatorUserId": "",
        "validcode": "",
        "passwordEncrypt": prequote_form_value(context.password_encrypt),
    }


def is_success_response(response: requests.Response) -> tuple[bool, dict[str, Any] | None]:
    text = response.text.strip()
    parsed: dict[str, Any] | None = None
    success = False

    if response.headers.get("Content-Type", "").lower().startswith("application/json") or text.startswith("{"):
        try:
            parsed = response.json()
            if isinstance(parsed, dict):
                status_value = (
                    parsed.get("result")
                    or parsed.get("success")
                    or parsed.get("status")
                    or parsed.get("ret_code")
                )
                success = str(status_value).lower() in {"0", "true", "success", "ok"}
        except Exception:  # noqa: BLE001
            parsed = None

    if not success and response.status_code == 200:
        keywords = ["成功", "online", "Login ok", "PortalUserV2", "success.jsp", "userIndex=", "keepaliveInterval="]
        success = any(keyword.lower() in text.lower() for keyword in keywords)

    return success, parsed


def login_once(session: requests.Session, config: Config, portal_entry_url: str | None) -> bool:
    context = fetch_portal_context(session, config, portal_entry_url)
    payload = build_payload(config, context)

    logger.info("开始发送登录请求 -> %s", context.login_url)
    logger.debug("使用的 portal 入口 URL: %s", context.entry_url)
    logger.debug("登录使用的 mac: %s", context.mac)

    response = session.post(
        url=context.login_url,
        data=payload,
        timeout=10,
        verify=False,
    )
    logger.info("HTTP 状态码: %s", response.status_code)
    logger.info("Content-Type: %s", response.headers.get("Content-Type", ""))

    success, parsed = is_success_response(response)
    if parsed is not None:
        logger.info("返回(JSON裁剪): %s", json.dumps(parsed, ensure_ascii=False)[:300])
    else:
        logger.info("返回(文本前 200 字): %s", response.text.strip()[:200])

    if success:
        logger.info("登录判定: 成功")
    else:
        logger.warning("登录判定: 失败")
    return success


def ensure_online_with_retry(
    session: requests.Session,
    config: Config,
    portal_entry_url: str | None,
) -> bool:
    for attempt in range(1, config.max_login_retries + 1):
        try:
            if login_once(session, config, portal_entry_url):
                return True
        except Exception as exc:  # noqa: BLE001
            logger.exception("第 %d 次登录请求异常: %s", attempt, exc)

        delay = config.base_retry_delay * (2 ** (attempt - 1))
        jitter = delay * config.retry_jitter * (random.random() * 2 - 1)
        sleep_seconds = max(1.0, delay + jitter)
        logger.info("第 %d 次登录失败，%.1f 秒后重试…", attempt, sleep_seconds)
        time.sleep(sleep_seconds)

    logger.error("所有 %d 次登录尝试均失败", config.max_login_retries)
    return False


def loop_guard(
    session: requests.Session,
    config: Config,
    interval: int,
    portal_entry_url: str | None,
) -> None:
    logger.info("进入守护循环，检测间隔 %d 秒。按 Ctrl+C 退出。", interval)
    last_login_success_time: float | None = None
    check_count = 0
    while True:
        try:
            check_count += 1
            if is_online(session, config):
                if check_count % 10 == 0:
                    logger.info(
                        "状态正常 (已检测 %d 次，运行时长约 %d 分钟)",
                        check_count,
                        check_count * interval // 60,
                    )
            else:
                logger.warning("检测到掉线，开始自动登录…")
                if ensure_online_with_retry(session, config, portal_entry_url):
                    last_login_success_time = time.time()
                else:
                    logger.error("本轮重试未能恢复联网")

            if last_login_success_time and (time.time() - last_login_success_time) > 6 * 3600:
                logger.info("超过 6 小时，主动刷新登录…")
                ensure_online_with_retry(session, config, portal_entry_url)
                last_login_success_time = time.time()
        except KeyboardInterrupt:
            logger.info("收到中断信号，退出守护循环。")
            break
        except Exception as exc:  # noqa: BLE001
            logger.exception("守护循环异常: %s", exc)
        time.sleep(interval)


def main() -> int:
    args = parse_args()
    config = load_config()
    log_file = setup_logging(config.log_dir)
    require_env_config(config)
    if args.verbose:
        logger.setLevel(logging.DEBUG)

    logger.info(
        "================ 启动: %s ================",
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )
    logger.info("当前用户: %s", config.user_id)
    logger.info("日志文件: %s", log_file)

    if args.startup_delay > 0:
        logger.info("启动延迟 %d 秒 (等待系统/网络就绪)…", args.startup_delay)
        time.sleep(args.startup_delay)

    session = create_session()
    if args.once:
        if is_online(session, config):
            logger.info("当前已在线，无需重复登录。")
            return 0
        return 0 if ensure_online_with_retry(session, config, args.portal_entry_url) else 1

    loop_guard(session, config, args.interval, args.portal_entry_url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
