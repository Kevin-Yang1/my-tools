#!/usr/bin/env python3

from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    tool_dir = repo_root / "tools" / "exp-scheduler"
    src_dir = tool_dir / "src"
    venv_command = tool_dir / ".venv" / "bin" / "exp-scheduler"

    if venv_command.exists():
        os.execv(str(venv_command), [str(venv_command), *sys.argv[1:]])

    if not src_dir.exists():
        print(
            "错误: 找不到 tools/exp-scheduler。请先运行: "
            "git submodule update --init --recursive",
            file=sys.stderr,
        )
        return 1

    sys.path.insert(0, str(src_dir))
    try:
        from exp_scheduler_app.cli import main as cli_main
    except ModuleNotFoundError as exc:
        missing = exc.name or "依赖"
        print(
            "错误: exp-scheduler 运行依赖未安装，缺少 "
            f"{missing!r}。\n"
            "请运行:\n"
            "  cd tools/exp-scheduler\n"
            "  python3 -m venv .venv\n"
            "  source .venv/bin/activate\n"
            "  pip install -e \".[dev]\"",
            file=sys.stderr,
        )
        return 1

    return cli_main(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
