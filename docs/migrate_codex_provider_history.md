# migrate_codex_provider_history.py

`scripts/tools/migrate_codex_provider_history.py` 用来批量迁移 Codex 本地历史里的 `model_provider` 字段，解决 provider key 改名或切换后，旧会话因为落在错误 bucket 中而无法正常显示的问题。

这个脚本会同时处理两类数据：

- `CODEX_HOME/sessions/` 和 `CODEX_HOME/archived_sessions/` 下的 rollout `jsonl`
- Codex 本地状态库 `state_*.sqlite` 里的 `threads.model_provider`

默认是预览模式，只有加上 `--apply` 才会真正写入。

## 适用场景

- 你把 Codex 配置里的 provider key 从别的名字切到了 `custom`
- 旧历史文件里的 `session_meta.payload.model_provider` 还是旧值
- SQLite 索引里的 `threads.model_provider` 还是旧值
- 配置已经可用，但历史列表仍然不显示或显示不全

这个脚本不会修改 `config.toml`，只迁移历史数据里的 provider 标记。

## 会读写什么

- 会读取本地 `config.toml`、rollout `jsonl` 和 `state_*.sqlite`
- 只有传入 `--apply` 时才会改写本地历史文件和 SQLite
- 如果传了 `--backup-dir`，会额外写入备份文件
- 不会删除会话
- 不会联网

## 运行方式

这是一个维护型工具，放在 `scripts/tools/` 下。现在也会被 `./install.sh` 安装成命令，命令名为 `migrate-codex-provider-history`。

直接运行脚本：

```bash
python3 scripts/tools/migrate_codex_provider_history.py --help
```

如果你已经执行过 `./install.sh`，也可以直接用命令名：

```bash
migrate-codex-provider-history --help
```

最常见的预览命令：

```bash
python3 scripts/tools/migrate_codex_provider_history.py
```

或：

```bash
migrate-codex-provider-history
```

真正执行写入：

```bash
python3 scripts/tools/migrate_codex_provider_history.py --apply
```

## 参数说明

- `--codex-home`: 指定 Codex 数据目录，默认读取 `CODEX_HOME`，否则回退到 `~/.codex`
- `--target-provider`: 迁移目标 provider key；默认读取 `config.toml` 的 `model_provider`，缺失时回退到 `custom`
- `--keep-provider`: 保留不迁移的 provider key，可重复传入；默认仅保留目标 provider，`openai` 会被迁移
- `--state-db`: 显式指定 `state_*.sqlite` 路径；默认自动发现
- `--backup-dir`: 真正写入时，把变更前文件备份到这个目录
- `--apply`: 执行真实写入；不传时仅预览

## 默认扫描与发现逻辑

### 目标 provider 解析顺序

脚本会按下面顺序决定“迁移到哪个 provider”：

1. 显式传入的 `--target-provider`
2. `<codex-home>/config.toml` 里的 `model_provider`
3. 兜底值 `openai`

### rollout 文件

脚本会扫描：

- `<codex-home>/sessions/**/*.jsonl`
- `<codex-home>/archived_sessions/**/*.jsonl`

只会改写其中 `type == "session_meta"` 的行；空行会原样保留。

### SQLite 状态库

如果没有手动传 `--state-db`，脚本会按下面顺序自动找最新的 `state_*.sqlite`：

1. `config.toml` 里的 `sqlite_home`
2. 环境变量 `CODEX_SQLITE_HOME`
3. `<codex-home>`

同一个目录里如果有多个 `state_*.sqlite`，会优先选版本号更高、更新时间更新的那个。

## 输出内容怎么看

脚本结束后会打印一份汇总，包含：

- 当前模式：预览 / 执行写入
- `config.toml` 检查结果
- rollout 扫描文件数、需要迁移文件数、实际改写文件数
- `session_meta` 里迁移前后的 provider 分布
- SQLite 里需要更新的行数、实际更新的行数
- SQLite 中 provider 分布的迁移前后对比

如果你在预览模式下看到：

- `需要迁移文件数 > 0`
- `需要更新行数 > 0`

说明脚本已经找到了需要修复的历史数据，这时再加 `--apply` 即可真正写入。

## 常见示例

### 1. 先预览默认 `~/.codex`

```bash
python3 scripts/tools/migrate_codex_provider_history.py
```

### 2. 把历史统一迁到 `custom`

```bash
python3 scripts/tools/migrate_codex_provider_history.py \
  --target-provider custom \
  --apply
```

### 3. 如果你想保留 `openai` 或其他已有 provider，不去动它们

```bash
python3 scripts/tools/migrate_codex_provider_history.py \
  --keep-provider openai \
  --keep-provider anthropic \
  --target-provider custom \
  --apply
```

### 4. 指定 Codex 数据目录并备份后再写入

```bash
python3 scripts/tools/migrate_codex_provider_history.py \
  --codex-home /path/to/.codex \
  --backup-dir /path/to/codex-provider-backup \
  --apply
```

### 5. 手动指定状态库

```bash
python3 scripts/tools/migrate_codex_provider_history.py \
  --state-db /path/to/state_14.sqlite \
  --apply
```

## 备份与回滚

如果传了 `--backup-dir`，脚本会在真正写入时备份：

- 被改动的 rollout `jsonl`
- 对应的 SQLite 文件，以及存在时的 `-wal` / `-shm` sidecar 文件

建议第一次执行时总是带上备份目录，例如：

```bash
python3 scripts/tools/migrate_codex_provider_history.py \
  --backup-dir /tmp/codex-provider-backup \
  --apply
```

如果结果不符合预期，可以手动把备份文件拷回原位置。

## 注意事项

- 这个脚本不会帮你修 `config.toml`；如果当前 `model_provider` 仍然不是目标值，脚本只会打印警告
- 默认会迁移 `openai`；如果你只想迁移别的 provider，请显式追加 `--keep-provider openai`
- 如果目标 provider 没有在 `config.toml` 的 `model_providers` 中定义，脚本会提示，但仍允许你迁移历史
- 未传 `--apply` 时不会写任何文件
- 未传 `--backup-dir` 时，写入是直接覆盖，请谨慎
- 如果没有找到 `state_*.sqlite`，rollout 文件迁移仍然会执行，SQLite 部分会显示 `<not found>`

## 失败时常见原因

- `config.toml` 路径不对，或 `--codex-home` 指错了目录
- `jsonl` 里存在真正损坏的 JSON 行，导致 JSON 解析失败
- SQLite 文件路径不对，或当前用户没有写权限
- 目标 provider 实际上并不是你想要的 bucket，导致迁移后仍看不到历史

建议流程是：

1. 先运行一次预览
2. 确认 `config.toml` 当前配置和目标 provider 一致
3. 带 `--backup-dir` 再执行 `--apply`
4. 重启 Codex 或重新打开对应窗口后再检查历史是否恢复
