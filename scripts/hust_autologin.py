#!/usr/bin/env python3

from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    tool_dir = repo_root / "tools" / "hust-autologin"
    src_dir = tool_dir / "src"

    venv_commands = [
        tool_dir / ".venv" / "bin" / "hust-autologin",
        tool_dir / ".venv" / "Scripts" / "hust-autologin.exe",
    ]
    for venv_command in venv_commands:
        if venv_command.exists():
            os.execv(str(venv_command), [str(venv_command), *sys.argv[1:]])

    if not src_dir.exists():
        print(
            "错误: 找不到 tools/hust-autologin/src。请确认子项目目录完整。",
            file=sys.stderr,
        )
        return 1

    sys.path.insert(0, str(src_dir))
    try:
        from hust_autologin.core import main as cli_main
    except ModuleNotFoundError as exc:
        missing = exc.name or "依赖"
        print(
            "错误: hust-autologin 运行依赖未安装，缺少 "
            f"{missing!r}。\n"
            "请运行:\n"
            "  cd tools/hust-autologin\n"
            "  python -m venv .venv\n"
            "  .venv\\Scripts\\python -m pip install -e .    # Windows\n"
            "  .venv/bin/python -m pip install -e .          # Linux/macOS",
            file=sys.stderr,
        )
        return 1

    return cli_main()


if __name__ == "__main__":
    raise SystemExit(main())
