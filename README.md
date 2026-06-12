# My Tools

个人常用脚本和小工具集合。

## 结构
- `scripts/`: 单文件小脚本
- `scripts/tools/`: 维护型辅助脚本，也会参与安装
- `tools/`: 独立小工具
- `docs/`: 说明文档

## 安装

先拉取 submodule，再把 `scripts/` 和 `scripts/tools/` 里所有可执行脚本安装成命令：

```bash
git submodule update --init --recursive
./install.sh
```

安装后可直接运行：

```bash
wait-and-run python train.py --model llama --bs 8
```

`wait_and-run` 之外，还会额外安装一个短别名 `war`。

如果 `wait-and-run` 不在 PATH 里，把下面这一行加到 `~/.bashrc` 或 `~/.zshrc`：

```bash
export PATH="$HOME/.local/bin:$PATH"
```

以后新增脚本时，直接放进 `scripts/` 或 `scripts/tools/`，赋予可执行权限，再跑一次 `./install.sh`。

## Scripts
- `scripts/wait_and_run.sh`: 等待 GPU 显存低于阈值后执行命令，必要时只对 OOM / 资源类错误重试。
- `scripts/exp_scheduler.py`: 启动 GPU 实验任务调度器，安装后命令名为 `exp-scheduler`。实际源码来自 `tools/exp-scheduler` submodule。

## Script Tools
- `scripts/tools/migrate_codex_provider_history.py`: 迁移 Codex 本地历史里的 `model_provider` 字段，修复 provider key 变更后旧会话无法正确加载的问题。安装后命令名为 `migrate-codex-provider-history`。

## Tools
- `tools/exp-scheduler/`: GPU 实验任务调度器，源码仓库为 `git@github.com:Kevin-Yang1/exp-scheduler.git`，本仓库通过 submodule 记录当前使用的提交。

详细说明见：

- [docs/wait_and_run.md](docs/wait_and_run.md)
- [docs/exp-scheduler.md](docs/exp-scheduler.md)
- [docs/migrate_codex_provider_history.md](docs/migrate_codex_provider_history.md)
