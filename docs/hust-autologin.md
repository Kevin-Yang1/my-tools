# hust-autologin

`hust-autologin` 已经从 `my-tools` 拆出为独立仓库，并作为 submodule 维护。`my-tools` 里保留命令 wrapper，日常使用仍然可以通过当前仓库的 `./install.sh` 安装命令。

独立源码仓库：

```text
https://github.com/Kevin-Yang1/hust-autologin.git
```

当前仓库中的 submodule 位置：

```text
tools/hust-autologin
```

## 安装与运行

第一次 clone `my-tools` 后先拉取 submodule：

```bash
cd <path-to-my-tools>
git submodule update --init --recursive
```

给 `hust-autologin` 安装运行依赖：

```bash
cd <path-to-my-tools>/tools/hust-autologin
python -m venv .venv

# Windows
.venv\Scripts\python -m pip install -e .

# Linux/macOS
.venv/bin/python -m pip install -e .
```

回到 `my-tools`，安装命令 wrapper：

```bash
cd <path-to-my-tools>
./install.sh
```

最终调用链是：

```text
hust-autologin
-> ~/.local/bin/hust-autologin
-> <path-to-my-tools>/scripts/hust_autologin.py
-> <path-to-my-tools>/tools/hust-autologin/.venv/bin/hust-autologin
-> hust_autologin.core
```

如果不安装 wrapper，也可以直接运行：

```bash
cd <path-to-my-tools>
python scripts/hust_autologin.py --once
python scripts/hust_autologin.py --loop --interval 30 --startup-delay 20
```

子项目里的直接入口仍然可用：

```bash
cd <path-to-my-tools>/tools/hust-autologin
python HUSTAutologin.py --once
```

## 自启动配置

Windows：

最简单方式是双击：

```text
<path-to-my-tools>\tools\hust-autologin\setup\windows_autostart.cmd
```

也可以手动运行：

```powershell
cd <path-to-my-tools>\tools\hust-autologin
powershell -ExecutionPolicy Bypass -File .\setup\windows_autostart.ps1 -RunNow
```

Windows 一键配置后的计划任务会把运行日志写到：

```text
<path-to-my-tools>\tools\hust-autologin\logs\hust_autologin.log
```

Linux：

```bash
cd <path-to-my-tools>/tools/hust-autologin
bash setup/linux_autostart.sh --run-now
```

Linux 一键配置后的 systemd user service 会把运行日志写到：

```text
<path-to-my-tools>/tools/hust-autologin/logs/hust_autologin.log
```

Linux 的一键脚本创建的是 systemd user service。若要用户未登录时也随系统启动，需要额外启用：

```bash
sudo loginctl enable-linger "$USER"
```

## 维护规则

- `hust-autologin` 的真实 Git 仓库是 `https://github.com/Kevin-Yang1/hust-autologin.git`。
- `my-tools` 只记录 `tools/hust-autologin` submodule 指向的 commit。
- 更新 `hust-autologin` 代码时，先在 submodule 仓库提交并推送，再回到 `my-tools` 提交 submodule 指针变化。
- 不要把 `hust-autologin` 源码复制回 `scripts/`，否则会重新变成双份源码。

更新 submodule 指针的常用流程：

```bash
cd <path-to-my-tools>/tools/hust-autologin
git pull

cd <path-to-my-tools>
git add tools/hust-autologin
git commit -m "chore: update hust-autologin submodule"
```
