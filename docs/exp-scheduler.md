# exp-scheduler

`exp-scheduler` 已经从 `my-tools` 拆出为独立仓库，并作为唯一源码维护。

本地源码位置：

```text
/SSD1/ykw/exp-scheduler
```

`my-tools` 不再保存 `exp-scheduler` 的后端、前端、测试、systemd 模板或 Codex skill 副本。之后改代码、跑测试、构建前端、安装 skill，都应该在独立仓库里完成。

## 安装与运行

```bash
cd /SSD1/ykw/exp-scheduler
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

exp-scheduler init
exp-scheduler doctor
exp-scheduler serve
```

如果之前通过 `my-tools/install.sh` 安装过旧的 `exp-scheduler` wrapper，可以重新运行一次：

```bash
cd /SSD1/ykw/my-tools
./install.sh
```

它只会在确认 `~/.local/bin/exp-scheduler` 是旧 wrapper 且仍指向 `scripts/exp_scheduler.py` 时移除它。之后 `exp-scheduler` 命令应由独立仓库的 `pip install -e .` 提供。

服务默认监听：

```text
127.0.0.1:17861
```

通过 SSH 隧道访问：

```bash
ssh -L 17861:127.0.0.1:17861 <server>
```

然后打开：

```text
http://127.0.0.1:17861
```

## 维护规则

- `exp-scheduler` 的真实代码只在 `/SSD1/ykw/exp-scheduler` 维护。
- `my-tools` 只保留这个索引页和 README 里的引用。
- 不要把 `exp-scheduler` 源码复制回 `tools/exp-scheduler/`。
- 如果以后创建 GitHub 远程仓库，在独立仓库里添加 remote 并推送；`my-tools` 不需要同步源码。

## 常用位置

- 独立仓库 README：`/SSD1/ykw/exp-scheduler/README.md`
- Python 后端：`/SSD1/ykw/exp-scheduler/src/exp_scheduler_app/`
- 前端源码：`/SSD1/ykw/exp-scheduler/frontend/`
- systemd 模板：`/SSD1/ykw/exp-scheduler/deploy/exp-scheduler.service`
- Codex skill：`/SSD1/ykw/exp-scheduler/skills/exp-scheduler-gpu-lease/`
