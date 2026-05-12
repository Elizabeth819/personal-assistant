#!/usr/bin/env bash
# batch.sh —— 把扫描清单切成 N 文件一批，输出可直接喂给 claude-mem 的 prompt 文件
# 每批生成一个 manifests/batch_NNN.txt，里面是绝对路径列表
# 用法：./ingest/batch.sh [批大小，默认50]

set -euo pipefail
cd "$(dirname "$0")/.."

SIZE="${1:-50}"
TSV="manifests/files.tsv"
[ ! -s "$TSV" ] && { echo "请先运行 ./ingest/scan.sh"; exit 1; }

rm -f manifests/batch_*.txt

# 按 mtime 降序（最近修改的优先入库）
sort -t$'\t' -k2,2nr "$TSV" | awk -F'\t' '{print $3}' \
  | split -l "$SIZE" -a 4 -d - manifests/batch_

# 重命名为 .txt
for f in manifests/batch_[0-9]*; do
  mv "$f" "${f}.txt"
done

n=$(ls manifests/batch_*.txt 2>/dev/null | wc -l | tr -d ' ')
echo "[batch] 已切分为 $n 批（每批 $SIZE 个文件）"
echo "[batch] 第一批预览："
head -5 "$(ls manifests/batch_*.txt | head -1)"
