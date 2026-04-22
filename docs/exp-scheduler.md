# exp-scheduler

`exp-scheduler` 是一个面向单用户实验服务器的 GPU 任务调度器。你把命令加入队列后，它会在检测到空闲 GPU 时自动启动任务，并通过一个只监听 `127.0.0.1` 的网页控制台提供增删改查、拖拽排序、取消任务、日志查看、环境模板复用、从现有 `conda` / `venv` 自动导入模板、给单个任务指定 GPU、实时调整全局可调度 GPU 白名单、紧急任务队列与手动抢占，以及按全局策略处理的 OOM / CUDA 资源类错误自动重试。其中运行中任务日志会以只读 PTY 终端展示，历史任务则继续使用纯文本日志视图。

网页头部会显示“当前控制服务器”的名称和 IP，方便你同时管理多台机器时快速区分。

## 目录
- 入口脚本：`scripts/exp_scheduler.py`
- 工具目录：`tools/exp-scheduler/`
- 用户级 systemd 模板：`tools/exp-scheduler/deploy/exp-scheduler.service`

## 依赖安装

```bash
cd /SSD1/ykw/my-tools
python3 -m venv .venv
source .venv/bin/activate
pip install -r tools/exp-scheduler/requirements-dev.txt
```

如果你希望只装运行依赖：

```bash
pip install -r tools/exp-scheduler/requirements.txt
```

## 初始化

初始化会创建默认配置、状态目录、日志目录和 SQLite 数据库。

```bash
./scripts/exp_scheduler.py init
```

默认配置文件路径：

```text
~/.config/exp-scheduler/config.toml
```

默认状态目录：

```text
~/.local/share/exp-scheduler
```

## 启动

先检查环境：

```bash
./scripts/exp_scheduler.py doctor
```

启动服务：

```bash
./scripts/exp_scheduler.py serve
```

如果你已经执行过 `./install.sh`，也可以直接用：

```bash
exp-scheduler serve
```

## SSH 隧道访问

服务默认只监听服务器本机回环地址：

```text
127.0.0.1:17861
```

在本机执行：

```bash
ssh -L 17861:127.0.0.1:17861 <server>
```

然后在本机浏览器打开：

```text
http://127.0.0.1:17861
```

## 开机自启

复制用户级 `systemd` 模板：

```bash
mkdir -p ~/.config/systemd/user
cp tools/exp-scheduler/deploy/exp-scheduler.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now exp-scheduler.service
```

查看状态：

```bash
systemctl --user status exp-scheduler.service
journalctl --user -u exp-scheduler.service -f
```

如果希望用户退出登录后服务仍然保持运行，可以开启 linger：

```bash
loginctl enable-linger "$USER"
```

## 页面功能
- 头部标识：显示当前控制服务器名和 IP
- 新建任务：命令、名称、环境模板、指定 GPU、普通/紧急队列、工作目录、环境变量、备注
- 环境配置：保存常用 `venv`、`conda` 或自定义 shell 激活步骤
- 发现现有环境：扫描当前常见目录和本机 `conda`，一键导入模板
- GPU 白名单：实时勾选哪些 GPU 允许被调度器分配，默认全部可用
- 队列管理：普通队列和紧急队列分开显示、分别拖拽调整顺序
- 运行中任务：查看分配 GPU、取消任务、查看只读终端、抢占回普通队列队首
- 历史任务：查看结果、查看纯文本日志、把失败/取消/中断任务重新入队
- 全局控制：暂停调度、恢复调度

## 日志视图

日志面板在 v1 里分成两种模式：
- 运行中任务：浏览器连接任务级 SSE，渲染只读 PTY 终端，可正确显示 ANSI 颜色、`tqdm` / `rich` 进度条以及 `\r` 覆盖刷新
- 历史任务：继续读取落盘日志文件，并在读取时归一化成可读纯文本，适合回看与搜索
- 浏览器侧不支持任意输入，也不会把键盘事件透传给任务；如果任务结束，页面会停掉实时终端流并切回历史纯文本视图

## 紧急任务队列与抢占

调度优先级规则：
- 紧急队列永远优先于普通执行队列
- 如果同时有多张空闲 GPU，调度器会先尽量启动紧急任务，再把剩余空闲卡分配给普通队列
- 紧急队列空了之后，调度器会继续按照普通执行队列顺序运行

推荐操作顺序：
1. 先在“新建任务”里勾选“加入紧急队列”，把紧急任务加入紧急队列
2. 再到“正在运行”里，对需要让路的任务点击“抢占回普通队首”
3. 被抢占的任务会被终止，并回到普通队列队首
4. 空出来的资源会优先给紧急队列

注意：
- 抢占是显式操作，不会因为你新建了紧急任务就自动杀掉当前任务
- 如果当前没有等待中的紧急任务，后端会拒绝抢占，避免误杀后又立刻把原任务重新拉起
- 抢占本质上是终止当前进程再重新排队，不是进程级 checkpoint / resume

## GPU 指定与全局白名单

任务级 GPU 规则：
- 默认是“自动分配”，调度器会从当前允许调度且空闲的 GPU 里选一张
- 如果在任务表单里指定了 GPU，该任务只会在对应 GPU 可用时启动
- 指定 GPU 的任务不会被偷偷改派到别的卡上

全局 GPU 白名单规则：
- 默认是“全部 GPU 可用”
- 你可以在网页 GPU 面板里实时勾选允许调度的 GPU，修改后立即生效，不需要重启服务
- 全局白名单只影响“新启动的任务”，不会强行打断已经在跑的任务
- 如果某个任务指定的 GPU 当前不在全局白名单里，它会继续留在队列中等待
- 任务完成后、以及全局 GPU 白名单变更后，调度器会立即尝试启动下一个符合条件的任务，不用等下一轮轮询

## 环境模板怎么用

环境模板由 4 部分组成：
- `配置名称`
- `默认工作目录`
- `激活命令`
- `默认环境变量`

任务创建时的规则是：
- 如果选择了环境模板，模板里的默认工作目录会作为任务目录
- 如果任务表单里又手填了工作目录，任务值优先
- 模板环境变量会先加载，任务表单里的环境变量会覆盖同名项
- 启动任务前会先执行模板里的 `激活命令`，再执行任务命令

## 自动重试

自动重试现在由服务端配置文件统一控制，不再按任务单独设置。修改：

```toml
auto_retry_max_retries = 0
auto_retry_delay_seconds = 5
```

这里的 `auto_retry_max_retries` 指的是：
- 首次运行失败后，额外允许再次尝试的次数
- `0` 表示关闭自动重试
- `1` 表示最多再试 1 次，总共最多跑 2 次

当前实现只会对 OOM / CUDA 资源类错误自动重试，判断逻辑与 [scripts/wait_and_run.sh](/SSD1/ykw/my-tools/scripts/wait_and_run.sh) 对齐，包括：
- 退出码 `137` / `143`
- 被信号杀掉的等价场景
- 日志中匹配 `cuda out of memory`、`failed to allocate`、`resource exhausted`、`oom-kill` 等模式

普通业务失败不会自动重试。

重试调度规则：
- 任务失败且满足重试条件时，会按设置的延迟重新回到队列头部
- 重新排队后仍然要等待空闲 GPU
- 每次尝试会生成独立日志文件，文件名带 `attempt_N`
- 历史里展示的是最后一次尝试结果
- 修改 `config.toml` 后需要重启 `exp-scheduler serve` 或 `systemd --user` 服务

### venv 示例

环境模板可以这样填：

```text
配置名称: torch-venv
默认工作目录: /SSD1/ykw/project-a
激活命令:
source /SSD1/ykw/project-a/.venv/bin/activate
默认环境变量:
PYTHONUNBUFFERED=1
HF_HOME=/SSD1/ykw/cache/hf
```

任务命令里直接填：

```bash
python train.py --model llama --bs 8
```

### 自动导入现有环境

在网页里的“环境配置”区点击“扫描现有环境”后，调度器会：
- 从 `conda info --json` 读取已有 `conda` 环境
- 在常见目录里扫描 `.venv`、`venv`、`.env`、`env`
- 自动生成推荐模板名、激活命令和默认目录

默认 venv 扫描目录通常包括：
- 当前启动目录
- 当前启动目录的上一级
- `HOME`
- `~/projects`、`~/code`、`~/work` 中存在的目录

扫描结果里可以：
- “导入模板”：直接创建环境模板
- “导入并编辑”：先把推荐内容填进表单，再自己补默认变量或备注

如果模板名冲突，导入接口会自动改名，例如 `conda:demo-2`。

### conda 示例

如果要用 `conda activate`，更稳的写法是先显式加载 `conda.sh`：

```text
配置名称: llm-conda
默认工作目录: /SSD1/ykw/project-b
激活命令:
source ~/miniconda3/etc/profile.d/conda.sh
conda activate llm
默认环境变量:
PYTHONUNBUFFERED=1
WANDB_MODE=offline
```

如果你更喜欢不用 shell 激活，也可以直接把任务命令写成：

```bash
conda run -n llm python train.py --config configs/a.yaml
```

这种情况下环境模板里的 `激活命令` 可以留空，只保留默认目录和环境变量。

## 服务器标识

如果你有多台服务器，建议在每台机器的 `config.toml` 里显式设置：

```toml
server_name = "lab-gpu-a"
server_ip = "10.10.0.23"
```

这两个字段会显示在网页头部，也会在 `doctor` 输出里显示。

如果配置文件里没有这两个字段，调度器会自动使用：
- 当前机器主机名作为 `server_name`
- 自动探测到的本机 IPv4 地址作为 `server_ip`

## 配置项

默认 `config.toml` 至少包含：

```toml
host = "127.0.0.1"
port = 17861
server_name = "your-hostname"
server_ip = "your-server-ip"
poll_interval_seconds = 5
gpu_idle_memory_mb = 2000
auto_retry_max_retries = 0
auto_retry_delay_seconds = 5
state_dir = "/home/<user>/.local/share/exp-scheduler"
log_dir = "/home/<user>/.local/share/exp-scheduler/logs"
```

## 故障排查

`doctor` 提示 `nvidia-smi` 缺失：
- 确认 NVIDIA 驱动是否安装，且当前用户能执行 `nvidia-smi`

页面打不开：
- 确认服务已经启动
- 确认 SSH 隧道仍然存在
- 确认 `config.toml` 中端口和隧道端口一致

任务一直排队不启动：
- 看 `/api/gpus` 或页面里的 GPU 卡片，确认显存是否低于阈值
- 看是否检测到外部进程占用 GPU
- 看队列是否被手动暂停

环境模板没生效：
- 先在 shell 里单独执行一遍模板的 `激活命令`
- `conda activate` 失败时，通常是没有先 `source .../conda.sh`
- 如果只需要指定解释器，优先考虑直接在任务命令里写绝对路径，如 `/path/to/venv/bin/python`

扫描不到你预期的 venv：
- 确认该虚拟环境目录名是 `.venv`、`venv`、`.env` 或 `env`
- 确认它距离扫描根目录不要太深
- 如果你的项目放在很特殊的位置，先在那个目录下启动 `exp-scheduler serve`，扫描范围会更贴近你的项目树

服务重启后任务变成 `interrupted`：
- 这是设计行为，避免服务重启后误重复执行
- 需要的任务可以在历史列表里手动重新入队

日志为空或不完整：
- 确认任务是否真的开始运行
- 检查 `log_dir` 是否可写
- 某些程序本身会缓冲输出，可以在命令里加 `PYTHONUNBUFFERED=1` 或 `python -u`
- 如果历史日志里看不到颜色或动态覆盖刷新，这是预期行为；这些效果只在运行中的只读终端视图里保留，历史视图会归一化为纯文本
