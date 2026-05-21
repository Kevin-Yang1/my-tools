#!/usr/bin/env bash

set -u -o pipefail

THRESHOLD_MB="${THRESHOLD_MB:-2000}"
CHECK_INTERVAL="${CHECK_INTERVAL:-10}"
GPU_ID="${GPU_ID:-}"
MAX_RETRIES="${MAX_RETRIES:-5}"
RETRY_DELAY="${RETRY_DELAY:-5}"
LOG_DIR="${LOG_DIR:-./wait_and_run_logs}"

mkdir -p "$LOG_DIR"

if ! command -v nvidia-smi >/dev/null 2>&1; then
  echo "错误: 找不到 nvidia-smi"
  exit 1
fi

if [ "$#" -eq 0 ]; then
  echo "用法:"
  echo "  $0 <command> [args...]"
  echo
  echo "示例:"
  echo "  $0 python train.py --model llama --bs 8"
  echo "  $0 bash scripts/next_step.sh --foo bar"
  echo
  echo "可选环境变量:"
  echo "  GPU_ID=1"
  echo "  THRESHOLD_MB=2000"
  echo "  CHECK_INTERVAL=10"
  echo "  MAX_RETRIES=10"
  echo "  RETRY_DELAY=5"
  echo "  LOG_DIR=./wait_and_run_logs"
  exit 1
fi

get_gpu_used_mem() {
  local gpu_id="$1"
  nvidia-smi -i "$gpu_id" --query-gpu=memory.used --format=csv,noheader,nounits 2>/dev/null \
    | head -n 1 | tr -d ' '
}

find_best_gpu() {
  local best_gpu=""
  local best_mem=""
  local gpu_list
  gpu_list=$(nvidia-smi --query-gpu=index --format=csv,noheader,nounits 2>/dev/null | tr -d ' ')

  for gid in $gpu_list; do
    local mem
    mem=$(get_gpu_used_mem "$gid")

    if ! [[ "$mem" =~ ^[0-9]+$ ]]; then
      continue
    fi

    if [ -z "$best_gpu" ] || [ "$mem" -lt "$best_mem" ]; then
      best_gpu="$gid"
      best_mem="$mem"
    fi
  done

  if [ -n "$best_gpu" ]; then
    echo "$best_gpu $best_mem"
    return 0
  fi

  return 1
}

wait_for_gpu() {
  while true; do
    if [ -n "$GPU_ID" ]; then
      local used_mem
      used_mem=$(get_gpu_used_mem "$GPU_ID")

      if [[ -z "$used_mem" ]]; then
        echo "无法读取 GPU ${GPU_ID} 状态，${CHECK_INTERVAL}s 后重试"
        sleep "$CHECK_INTERVAL"
        continue
      fi

      if ! [[ "$used_mem" =~ ^[0-9]+$ ]]; then
        echo "GPU ${GPU_ID} 显存值异常: ${used_mem}，${CHECK_INTERVAL}s 后重试"
        sleep "$CHECK_INTERVAL"
        continue
      fi

      if [ "$used_mem" -lt "$THRESHOLD_MB" ]; then
        SELECTED_GPU="$GPU_ID"
        SELECTED_MEM="$used_mem"
        return 0
      fi

      echo "GPU ${GPU_ID} 当前显存占用 ${used_mem} MiB，未低于阈值 ${THRESHOLD_MB} MiB，${CHECK_INTERVAL}s 后重试"
      sleep "$CHECK_INTERVAL"
    else
      local best_info
      best_info=$(find_best_gpu || true)

      if [ -z "$best_info" ]; then
        echo "无法读取 GPU 信息，${CHECK_INTERVAL}s 后重试"
        sleep "$CHECK_INTERVAL"
        continue
      fi

      local best_gpu best_mem
      best_gpu=$(echo "$best_info" | awk '{print $1}')
      best_mem=$(echo "$best_info" | awk '{print $2}')

      if [ "$best_mem" -lt "$THRESHOLD_MB" ]; then
        SELECTED_GPU="$best_gpu"
        SELECTED_MEM="$best_mem"
        return 0
      fi

      echo "当前最空闲 GPU 是 ${best_gpu}，显存占用 ${best_mem} MiB，未低于阈值 ${THRESHOLD_MB} MiB，${CHECK_INTERVAL}s 后重试"
      sleep "$CHECK_INTERVAL"
    fi
  done
}

is_retryable_oom_error() {
  local status="$1"
  local logfile="$2"

  # 1) 常见“被系统杀掉”
  # 137 = 128 + 9  -> SIGKILL
  # 143 = 128 + 15 -> SIGTERM
  if [ "$status" -eq 137 ] || [ "$status" -eq 143 ]; then
    return 0
  fi

  # 2) 根据日志判断是否属于 OOM / CUDA 资源类错误
  if grep -Eiq \
    "out of memory|cuda out of memory|cublas.*alloc|cuda error: out of memory|failed to allocate|cuda runtime error|memory allocation|std::bad_alloc|nccl.*unhandled system error|device-side assert triggered|resource exhausted|cuda error.*launch out of resources|cuda-capable device.*busy or unavailable|cudaerrordevicesunavailable" \
    "$logfile"; then
    return 0
  fi

  # 3) 有时会出现进程被 kill 的字样
  if grep -Eiq \
    "killed|terminated|oom-kill|out of memory: kill process" \
    "$logfile"; then
    return 0
  fi

  return 1
}

attempt=1

if [ -n "$GPU_ID" ]; then
  echo "已指定 GPU_ID=$GPU_ID"
else
  echo "未指定 GPU_ID，将自动寻找最空闲 GPU"
fi

echo "启动条件: GPU 显存占用低于 ${THRESHOLD_MB} MiB"
echo "最大重试次数: ${MAX_RETRIES}"
echo "仅对 OOM/资源类错误重试"
echo "异常退出后的重试间隔: ${RETRY_DELAY}s"
echo "日志目录: ${LOG_DIR}"
printf '待执行命令: '
printf '%q ' "$@"
printf '\n'

while [ "$attempt" -le "$MAX_RETRIES" ]; do
  echo
  echo "========== 第 ${attempt}/${MAX_RETRIES} 次尝试 =========="

  wait_for_gpu

  timestamp=$(date +"%Y%m%d_%H%M%S")
  logfile="${LOG_DIR}/attempt_${attempt}_gpu${SELECTED_GPU}_${timestamp}.log"

  echo "选择 GPU ${SELECTED_GPU}（当前显存占用 ${SELECTED_MEM} MiB），开始执行"
  printf '执行命令: CUDA_VISIBLE_DEVICES=%s ' "$SELECTED_GPU"
  printf '%q ' "$@"
  printf '\n'
  echo "日志文件: ${logfile}"

  # 用 subshell 包起来，方便把环境变量只作用于这次命令
  (
    export CUDA_VISIBLE_DEVICES="$SELECTED_GPU"
    "$@"
  ) 2>&1 | tee "$logfile"

  status=${PIPESTATUS[0]}

  if [ "$status" -eq 0 ]; then
    echo "任务正常完成"
    exit 0
  fi

  echo "任务异常退出，退出码: $status"

  if is_retryable_oom_error "$status" "$logfile"; then
    echo "判断结果: 属于 OOM/资源类错误，允许重试"

    if [ "$attempt" -ge "$MAX_RETRIES" ]; then
      echo "已达到最大重试次数，停止重试"
      exit "$status"
    fi

    echo "${RETRY_DELAY}s 后重新进入等待队列"
    sleep "$RETRY_DELAY"
    attempt=$((attempt + 1))
    continue
  fi

  echo "判断结果: 不属于 OOM/资源类错误，不重试，直接退出"
  exit "$status"
done
