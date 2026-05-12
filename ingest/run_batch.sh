#!/usr/bin/env bash
# run_batch.sh —— 自动按批次调用 claude headless 模式处理
# 用法：./ingest/run_batch.sh [起始批号] [结束批号]
# 例：./ingest/run_batch.sh 0 5  处理 batch_0000 ~ batch_0005

set -euo pipefail
cd "$(dirname "$0")/.."

# claude 是 zsh 函数，bash 脚本里只能用绝对路径
CLAUDE_BIN="${CLAUDE_BIN:-/usr/local/bin/claude}"

# 确保 copilot-api 在跑
if ! lsof -i :4142 -sTCP:LISTEN &>/dev/null; then
  echo "[run] 启动 copilot-api..."
  copilot-api start --port 4142 --proxy-env &>/dev/null &
  for i in 1 2 3 4 5 6 7 8 9 10; do
    lsof -i :4142 -sTCP:LISTEN &>/dev/null && break
    sleep 1
  done
fi

START="${1:-0}"
END="${2:-0}"

for i in $(seq "$START" "$END"); do
  BATCH=$(printf "manifests/batch_%04d.txt" "$i")
  [ ! -f "$BATCH" ] && { echo "[skip] 没有 $BATCH"; continue; }

  LOG="logs/batch_$(printf %04d "$i").log"
  echo "[run] 处理 $BATCH -> $LOG"

  PROMPT=$(sed "s|~/repository/personal-assistant/manifests/batch_0000.txt|$PWD/$BATCH|g" ingest/PROMPT_TEMPLATE.md)

  # headless 模式
  echo "$PROMPT" | "$CLAUDE_BIN" --dangerously-skip-permissions -p \
    --append-system-prompt "你正在做长期记忆灌输任务，重点是结构化提炼，不是写代码。" \
    > "$LOG" 2>&1

  echo "[done] 批 $i 完成，日志: $LOG ($(wc -l < "$LOG") 行)"
done

echo "[all] 完成 $START ~ $END，请打开 http://localhost:37701 查看 memory 增长。"
