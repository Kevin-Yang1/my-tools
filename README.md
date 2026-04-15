# My Tools

个人常用脚本和小工具集合。

## 结构
- `scripts/`: 单文件小脚本
- `tools/`: 独立小工具
- `docs/`: 说明文档

## 安装

把 `scripts/` 里所有可执行脚本安装成命令：

```bash
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

以后新增脚本时，直接放进 `scripts/` 并赋予可执行权限，再跑一次 `./install.sh`。

## Scripts
- `scripts/wait_and_run.sh`: 等待 GPU 显存低于阈值后执行命令，必要时只对 OOM / 资源类错误重试。
