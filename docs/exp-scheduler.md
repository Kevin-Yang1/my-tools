# exp-scheduler

`exp-scheduler` 已经从 `my-tools` 拆出为独立仓库，并作为唯一源码维护。`my-tools` 里保留的是 submodule 指针，所以源码仓库分离，但日常使用仍然可以通过当前仓库的 `./install.sh` 安装命令。

独立源码仓库：

```text
git@github.com:Kevin-Yang1/exp-scheduler.git
```

当前仓库中的 submodule 位置：

```text
tools/exp-scheduler
```

`my-tools` 不保存第二份源码，只保存 submodule 的 commit 指针。之后改代码、跑测试、构建前端、安装 skill，都应该在 `tools/exp-scheduler` 或独立仓库 `<path-to-exp-scheduler>` 里完成。

## 安装与运行

第一次 clone `my-tools` 后先拉取 submodule：

```bash
cd <path-to-my-tools>
git submodule update --init --recursive
```

给 `exp-scheduler` 安装运行依赖：

```bash
cd <path-to-my-tools>/tools/exp-scheduler
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

回到 `my-tools`，安装命令 wrapper：

```bash
cd <path-to-my-tools>
./install.sh
```

这些命令分别做什么：

- `git submodule update --init --recursive`：按 `.gitmodules` 里的配置拉取 `tools/exp-scheduler`。`my-tools` 只保存 submodule 指针，普通 clone 后这个目录可能还没有实际源码；这条命令会把 `git@github.com:Kevin-Yang1/exp-scheduler.git` 的对应 commit 拉下来。
- `cd <path-to-my-tools>/tools/exp-scheduler`：进入 `exp-scheduler` 的真实源码目录。后端、前端、测试、systemd 模板和 skill 都在这里。
- `python3 -m venv .venv`：在 submodule 里创建独立 Python 虚拟环境，路径是 `tools/exp-scheduler/.venv`。这样调度器依赖不会污染系统 Python，也不依赖 `my-tools` 根目录环境。
- `source .venv/bin/activate`：激活这个虚拟环境，让当前 shell 优先使用 `.venv/bin/python` 和 `.venv/bin/pip`。
- `pip install -e ".[dev]"`：以 editable 模式安装当前项目，并安装开发依赖。`-e` 表示代码仍然使用当前源码目录，改后端源码后不用重新安装；`[dev]` 会额外安装测试依赖，例如 `pytest` 和 `httpx`。只运行服务时也可以用 `pip install -e .`。
- `cd <path-to-my-tools>`：回到 `my-tools` 仓库根目录，准备运行当前仓库的安装脚本。
- `./install.sh`：把 `scripts/` 和 `scripts/tools/` 下的可执行脚本安装到 `~/.local/bin`。其中 `scripts/exp_scheduler.py` 会被安装成 `~/.local/bin/exp-scheduler`。

最终调用链是：

```text
exp-scheduler
-> ~/.local/bin/exp-scheduler
-> <path-to-my-tools>/scripts/exp_scheduler.py
-> <path-to-my-tools>/tools/exp-scheduler/.venv/bin/exp-scheduler
-> exp_scheduler_app.cli
```

之后可以像以前一样从任意目录运行：

```bash
exp-scheduler init
exp-scheduler doctor
exp-scheduler serve
```

如果不想安装到 `~/.local/bin`，也可以直接运行：

```bash
cd <path-to-my-tools>
./scripts/exp_scheduler.py doctor
./scripts/exp_scheduler.py serve
```

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

- `exp-scheduler` 的真实 Git 仓库是 `git@github.com:Kevin-Yang1/exp-scheduler.git`。
- `my-tools` 只记录 `tools/exp-scheduler` submodule 指向的 commit。
- 更新 `exp-scheduler` 代码时，先在 submodule 仓库提交并推送，再回到 `my-tools` 提交 submodule 指针变化。
- 不要把 `exp-scheduler` 源码复制成普通目录，否则会重新变成双份源码。

更新 submodule 指针的常用流程：

```bash
cd <path-to-my-tools>/tools/exp-scheduler
git pull

cd <path-to-my-tools>
git add tools/exp-scheduler
git commit -m "chore: 更新 exp-scheduler submodule"
```

## 常用位置

- submodule README：`<path-to-my-tools>/tools/exp-scheduler/README.md`
- Python 后端：`<path-to-my-tools>/tools/exp-scheduler/src/exp_scheduler_app/`
- 前端源码：`<path-to-my-tools>/tools/exp-scheduler/frontend/`
- systemd 模板：`<path-to-my-tools>/tools/exp-scheduler/deploy/exp-scheduler.service`
- Codex skill：`<path-to-my-tools>/tools/exp-scheduler/skills/exp-scheduler-gpu-lease/`
