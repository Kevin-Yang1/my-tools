# wait_and_run_retry_oom_only.sh 使用说明

## 简介

这是一个用于共享 GPU 服务器环境的任务调度脚本，解决以下常见问题：

* GPU 被别人占用，任务无法立即启动
* 程序运行中途被挤掉（显存不足 / OOM）
* 想自动等待空闲 GPU 再运行任务
* 想失败后自动重试，但只对资源问题重试
* 想自动选择最空闲 GPU

---

# 核心功能

## 1. 自动等待 GPU 空闲

脚本持续检测 GPU 显存占用。

当显存低于设定阈值时，自动启动任务。

## 2. 自动选择 GPU

默认行为：

* 自动扫描所有 GPU
* 找到当前显存占用最低的 GPU
* 若满足阈值则启动任务

## 3. 支持手动指定 GPU

可通过环境变量指定：

```bash
GPU_ID=1
```

则脚本只监控并使用 GPU 1。

## 4. 自动绑定 GPU

脚本内部自动设置：

```bash
CUDA_VISIBLE_DEVICES=<选中的GPU>
```

任务只会看到并使用该 GPU。

## 5. 失败自动重试（仅限资源类错误）

以下情况会自动重试：

* CUDA out of memory
* 显存不足
* 进程被 kill（137 / 143）
* allocation failed
* resource exhausted

以下情况不会重试：

* 代码 bug
* 参数错误
* 文件不存在
* Python 逻辑异常

## 6. 自动记录日志

每次尝试都会生成日志文件，例如：

```bash
./wait_and_run_logs/attempt_2_gpu1_20260416_150300.log
```

---

# 使用方法

## 给脚本执行权限

```bash
chmod +x wait_and_run_retry_oom_only.sh
```

## 自动选最空闲 GPU

```bash
./wait_and_run_retry_oom_only.sh python train.py --model llama
```

## 指定 GPU

```bash
GPU_ID=1 ./wait_and_run_retry_oom_only.sh python train.py
```

## 执行 bash 脚本

```bash
./wait_and_run_retry_oom_only.sh bash scripts/run.sh --foo bar
```

## Torch 分布式任务

```bash
./wait_and_run_retry_oom_only.sh torchrun --nproc_per_node=1 train.py
```

---

# 可选参数（环境变量）

## GPU_ID

指定使用哪张 GPU。默认自动选卡。

## THRESHOLD_MB

显存占用低于该值才启动任务。

默认：`2000`（MiB）

## CHECK_INTERVAL

轮询 GPU 状态间隔（秒）

默认：`10`

## MAX_RETRIES

最多重试次数（仅资源类错误）

默认：`5`

## RETRY_DELAY

任务失败后等待多久再重新排队（秒）

默认：`5`

## LOG_DIR

日志目录。

默认：`./wait_and_run_logs`

---

# 运行流程

```text
启动脚本
   ↓
检查命令参数
   ↓
寻找可用 GPU
   ↓
满足阈值？
   ↓ 否
继续等待
   ↓ 是
启动任务
   ↓
任务成功？
   ↓ 是 → 结束
   ↓ 否
是否属于 OOM / 被 kill？
   ↓ 否 → 退出
   ↓ 是
等待后重新排队
```

---

# 注意事项

## 1. 推荐训练脚本支持 checkpoint

否则任务失败重试时会从头开始。

## 2. 默认只适合单卡任务

如果你要多卡训练，需要自行修改 GPU 分配逻辑。

## 3. 显存阈值建议

| GPU 类型 | 推荐阈值 |
| ------ | ---- |
| 24GB 卡 | 2000 |
| 48GB 卡 | 4000 |
| 80GB 卡 | 6000 |

---

# 推荐使用方式

```bash
GPU_ID=1 MAX_RETRIES=10 ./wait_and_run_retry_oom_only.sh python train.py --resume latest.pt
```
