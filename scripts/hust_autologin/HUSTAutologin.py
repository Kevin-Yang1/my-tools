"""
校园网自动重连脚本（守护模式）
=================================================
功能:
 1. 定时检测外网连通性（HTTP 测试 + 可选 ping）。
 2. 发现掉线后自动调用认证接口重新登录。
 3. 带日志轮转、失败重试、指数退避与随机抖动。
 4. 支持命令行参数: --once 仅登录一次, --loop 持续守护(默认), --interval 间隔秒数。
 5. 支持通过环境变量提供敏感信息，避免明文写死：
      CAMPUS_USER_ID, CAMPUS_PASSWORD_HASH, CAMPUS_QUERY_STRING

使用建议:
   1) 先手动抓包确认 userId / password(加密串) / queryString。
   2) 将它们放入环境变量或本文件常量区。
   3) 在 Windows 任务计划程序中设置开机或登录自动运行 (见文末注释 run_as_startup 说明)。

安全提示: 加密后的 password 依旧可能被他人复用，请勿将本文件随意公开。
"""

from __future__ import annotations
import os
import sys
import io
import time
import random
import json
import logging
from logging.handlers import RotatingFileHandler
from argparse import ArgumentParser
from datetime import datetime
import subprocess
from typing import Any, Dict
from urllib.parse import quote, urlparse

import requests  # 如果未安装: pip install requests

# 使控制台输出保持 UTF-8（某些 PowerShell 环境下有用）
try:
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace"
        )
except Exception:  # noqa: BLE001
    pass

# ================== 可配置区域 ==================
PORTAL_ENTRY_URL = "http://172.18.18.60:8080/eportal/index.jsp?wlanuserip=b044e7eb21504b5eb6b23d7f589fcd8c&wlanacname=90e89a42a2b53b8eeaeb783ea002a860&ssid=&nasip=37b709e4c1d7c99666cfa26311ad83a8&snmpagentip=&mac=a2911ba10d4a2a0e64a1cd9318509fab&t=wireless-v2&url=2c0328164651e2b4f13b933ddf36628bea622dedcc302b30&apmac=&nasid=90e89a42a2b53b8eeaeb783ea002a860&vid=0677c4deec3c11fa&port=802251fcf33a69a2&nasportid=5b9da5b08a53a540e5ed3ad9c53cf9a443bdc3cb16b0474bafcfba526f65e58e"
LOGIN_URL = "http://172.18.18.60:8080/eportal/InterFace.do?method=login"

# 如果不使用环境变量，可在此直接填写常量；优先读取环境变量。
USER_ID = os.getenv("CAMPUS_USER_ID", "M202477024")
PASSWORD_HASH = os.getenv(
    "CAMPUS_PASSWORD_HASH",
    "2d2578df9a68e584d72518dfe9251b4ecc2dec94ac6ddc34d2e33c6ced1dfac425ecce4d1573112e4a62cf16123fe03dff38637dfd26bb6a598c0885856850bd3deeff980ba1322f298d58ec82ce89d369442f63deb17f86c1fd546fd8fe4546d93e54cf7459114548276fa89fd0ceb9786ea07fc790c00f74f2a836b89ae0bc",
)
def _build_default_query_string(entry_url: str) -> str:
    raw_query = urlparse(entry_url).query.strip()
    return quote(raw_query, safe="") if raw_query else ""


QUERY_STRING = os.getenv("CAMPUS_QUERY_STRING") or _build_default_query_string(
    PORTAL_ENTRY_URL
)

# 检测外网可用性的 URL（需能被正常访问的公共站点）
# 注意：校园网环境下 ping 可能畅通但 HTTP 被拦截，因此不使用 ping 检测
CONNECTIVITY_TEST_URL = "http://www.baidu.com"  # 使用 HTTP 避免 SSL 证书问题
CONNECTIVITY_TIMEOUT = 4  # 秒

# 日志设置
LOG_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(LOG_DIR, "autologin.log")
MAX_LOG_BYTES = 512 * 1024
BACKUP_COUNT = 3

# 登录失败重试参数
MAX_LOGIN_RETRIES = 5
BASE_RETRY_DELAY = 2  # 首次失败后等待秒数
RETRY_JITTER = 0.4  # 抖动系数 (0~0.4)

# 守护循环默认检测间隔（秒）
DEFAULT_INTERVAL = 30

# ================== 日志初始化 ==================
logger = logging.getLogger("autologin")
logger.setLevel(logging.INFO)
_formatter = logging.Formatter(
    fmt="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
if not logger.handlers:
    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=MAX_LOG_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
    )
    file_handler.setFormatter(_formatter)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(_formatter)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)


def build_payload() -> Dict[str, Any]:
    """构造登录请求数据。某些字段如果后续抓包发现有变化，可在此动态生成。"""
    return {
        "userId": USER_ID,
        "password": PASSWORD_HASH,
        "service": "",
        "queryString": QUERY_STRING,
        "operatorPwd": "",
        "operatorUserId": "",
        "validcode": "",
        "passwordEncrypt": "true",
    }


def is_online() -> bool:
    """通过 HTTP 测试判断是否已连外网。

    注意：校园网环境下 ping 可能畅通但实际无法访问互联网服务，
    因此仅使用 HTTP 请求进行检测。
    """
    try:
        # verify=False 禁用 SSL 验证，避免校园网中间人证书问题
        # allow_redirects=False 防止被重定向到认证页面后误判为成功
        r = requests.get(
            CONNECTIVITY_TEST_URL,
            timeout=CONNECTIVITY_TIMEOUT,
            verify=False,
            allow_redirects=False,
        )
        # 200-299 都认为是成功（百度可能返回 302 等）
        if not (200 <= r.status_code < 400):
            return False

        # 检查响应内容，排除校园网认证页面
        # 校园网通常返回重定向到 eportal 的 HTML/JavaScript
        text = r.text.lower()
        portal_keywords = [
            "eportal",  # 校园网认证门户
            "wlanuserip",  # 认证参数
            "172.18.18.6",  # 校园网认证服务器 IP
            "portaluserv2",  # 认证接口
            "drcom",  # Dr.COM 认证系统
            "srun_portal",  # 深澜认证
        ]

        # 如果响应包含任何认证页面特征，视为离线
        for keyword in portal_keywords:
            if keyword in text:
                return False

        return True
    except Exception:
        # 任何异常（连接失败、超时等）都视为离线
        return False


def login_once() -> bool:
    """执行一次登录，返回是否成功。尝试解析 JSON；否则仅依据 HTTP 200。"""
    payload = build_payload()
    logger.info("开始发送登录请求 -> %s", LOGIN_URL)
    try:
        resp = requests.post(url=LOGIN_URL, data=payload, timeout=10)
    except Exception as e:  # noqa: BLE001
        logger.error("网络异常: %s", e)
        return False

    logger.info("HTTP 状态码: %s", resp.status_code)
    text = resp.text.strip()

    logger.info("Content-Type: %s", resp.headers.get("Content-Type", ""))
    success = False
    parsed: Dict[str, Any] | None = None
    if resp.headers.get("Content-Type", "").lower().startswith(
        "application/json"
    ) or text.startswith("{"):
        try:
            parsed = resp.json()
            # 下面几个键名是假设，具体以真实返回为准，可打印观察
            # 常见: result: 'success' 或 'fail'; 或 ret_code 等
            if isinstance(parsed, dict):
                status_val = (
                    parsed.get("result")
                    or parsed.get("success")
                    or parsed.get("status")
                    or parsed.get("ret_code")
                )
                # 粗略判定
                if str(status_val).lower() in {"0", "true", "success", "ok"}:
                    success = True
        except Exception:  # noqa: BLE001
            pass

    if not success and resp.status_code == 200:
        # 如果 200 且正文包含某些关键字也可判断成功（需要你根据实际返回调整）
        keywords = ["成功", "online", "Login ok", "PortalUserV2"]
        keywords.extend(["success.jsp", "userIndex=", "keepaliveInterval="])
        for kw in keywords:
            if kw.lower() in text.lower():  # 简单匹配
                success = True
                break

    if parsed is not None:
        logger.info("返回(JSON裁剪): %s", json.dumps(parsed, ensure_ascii=False)[:300])
    else:
        logger.info("返回(文本前 200 字): %s", text[:200])

    if success:
        logger.info("登录判定: 成功")
    else:
        logger.warning("登录判定: 失败 (请抓包核对 payload 或关键字规则)")
    return success


def ensure_online_with_retry() -> bool:
    """掉线后多次重试登录。"""
    for attempt in range(1, MAX_LOGIN_RETRIES + 1):
        ok = login_once()
        if ok:
            return True
        delay = BASE_RETRY_DELAY * (2 ** (attempt - 1))
        # 抖动: 随机 +/- (RETRY_JITTER * delay)
        jitter = delay * RETRY_JITTER * (random.random() * 2 - 1)
        sleep_s = max(1, delay + jitter)
        logger.info("第 %d 次登录失败，%.1f 秒后重试…", attempt, sleep_s)
        time.sleep(sleep_s)
    logger.error("所有 %d 次登录尝试均失败", MAX_LOGIN_RETRIES)
    return False


def loop_guard(interval: int) -> None:
    logger.info("进入守护循环，检测间隔 %d 秒。按 Ctrl+C 退出。", interval)
    last_login_success_time: float | None = None
    check_count = 0  # 检测计数器
    while True:
        try:
            check_count += 1
            if is_online():
                logger.debug("网络正常")
                # 每10次检测（约5分钟）记录一次状态，证明脚本在运行
                if check_count % 10 == 0:
                    logger.info(
                        "状态正常 (已检测 %d 次，运行时长约 %d 分钟)",
                        check_count,
                        check_count * interval // 60,
                    )
            else:
                logger.warning("检测到掉线，开始自动登录…")
                if ensure_online_with_retry():
                    last_login_success_time = time.time()
                else:
                    logger.error("本轮重试未能恢复联网")
            # 可选: 定期刷新登录（例如 6 小时），防止会话过期
            if (
                last_login_success_time
                and (time.time() - last_login_success_time) > 6 * 3600
            ):
                logger.info("超过 6 小时，主动刷新登录…")
                ensure_online_with_retry()
                last_login_success_time = time.time()
        except KeyboardInterrupt:
            logger.info("收到中断信号，退出守护循环。")
            break
        except Exception as e:  # noqa: BLE001
            logger.exception("守护循环异常: %s", e)
        time.sleep(interval)


def parse_args():
    p = ArgumentParser(description="校园网自动重连脚本")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--once", action="store_true", help="只执行一次登录尝试后退出")
    g.add_argument("--loop", action="store_true", help="持续守护模式 (默认)")
    p.add_argument(
        "--interval",
        type=int,
        default=DEFAULT_INTERVAL,
        help="守护模式检测间隔秒数 (默认 30)",
    )
    p.add_argument("--verbose", action="store_true", help="启用 DEBUG 日志输出")
    p.add_argument(
        "--startup-delay",
        type=int,
        default=0,
        help="(可选) 启动后先延迟 N 秒再开始，用于开机自启时等待网络栈稳定",
    )
    return p.parse_args()


def main():
    args = parse_args()
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    logger.info(
        "================ 启动: %s ================",
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )
    logger.info("当前用户: %s", USER_ID)
    if args.startup_delay > 0:
        logger.info("启动延迟 %d 秒 (等待系统/网络就绪)…", args.startup_delay)
        time.sleep(args.startup_delay)
    if args.once:
        ensure_online_with_retry()
    else:
        loop_guard(args.interval)


if __name__ == "__main__":
    main()

"""
================ Windows 开机自启配置指南 ===========r======
方法一: 任务计划程序 (推荐)
 1. Win + R 输入: taskschd.msc 回车。
 2. 创建任务 -> 常规:
      名称: CampusAutoLogin
      勾选: 使用最高权限运行。
 3. 触发器: 新建 -> "登录时"。
 4. 操作: 新建 -> 程序/脚本 选择你的 python 可执行文件，例如:
        C:\\Python311\\python.exe
      添加参数(可选): "d:\\Users\\Dell\\Desktop\\研一\\scripts\\Autologin.py --loop --interval 30"
      起始于(可选):   d:\\Users\\Dell\\Desktop\\研一\\scripts
 5. 条件: 取消勾选 "仅当计算机使用交流电源时" (如果你用笔记本并希望在电池下也运行)。
 6. 设置: 勾选 "允许按需运行任务"、失败后重试等按需配置。

方法二: 启动文件夹
 1. Win + R 输入: shell:startup
 2. 在打开的目录中创建快捷方式，目标填写:
       C:\\Python311\\python.exe d:\\Users\\Dell\\Desktop\\研一\\scripts\\Autologin.py --loop --interval 30
 3. 保存即可。此法无法方便设置最高权限。

方法三: 打包成 exe (可选)
   pip install pyinstaller
   在脚本目录运行: pyinstaller -F Autologin.py
   然后将 dist/Autologin.exe 放入启动文件夹。

================ 常见问题 =================
1) 登录一直失败?
   - 用浏览器抓包确认 queryString 是否变化 (尤其含有动态 wlanuserip 等)。
   - 抓到最新值后更新环境变量或本文件。
   - 查看 autologin.log 中的返回内容，必要时放宽 / 调整 success 关键字。

2) 密码是否可以用明文?
   - 如果服务器要求加密，请继续使用抓包时的加密串；也可在浏览器源码里找到 JS 加密逻辑并在本地实现（进阶）。

3) 如何使用环境变量?
   - PowerShell 临时设置: $env:CAMPUS_USER_ID="xxxx"; $env:CAMPUS_PASSWORD_HASH="..."; $env:CAMPUS_QUERY_STRING="..."; python Autologin.py
   - 永久: 在系统高级设置 -> 环境变量中添加三个用户变量。

祝使用顺利。
"""
