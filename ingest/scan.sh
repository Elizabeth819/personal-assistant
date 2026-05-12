#!/usr/bin/env bash
# scan.sh —— 扫描白名单目录，生成"知识候选清单"
# 输出：manifests/files.tsv  (每行: <size>\t<mtime>\t<path>)
#       manifests/summary.txt（按目录/扩展名统计）
#
# 关键过滤：
#   - 只收文本类扩展（md/txt/pdf/code等）
#   - 排除常见缓存/构建/依赖目录
#   - 排除 > 2MB 的单文件（避免大日志/数据集）
#   - 排除明显敏感：*.key *.pem *.env id_rsa* *credentials*

set -euo pipefail
cd "$(dirname "$0")/.."

OUT_TSV="manifests/files.tsv"
OUT_SUM="manifests/summary.txt"
SOURCES="ingest/sources.txt"

# 允许的扩展名（小写）
EXTS_RE='\.(md|markdown|txt|rst|org|tex|pdf|epub|doc|docx|odt|rtf|html|htm|json|yaml|yml|toml|csv|tsv|ipynb|py|js|ts|jsx|tsx|go|rs|java|kt|swift|c|h|cpp|hpp|cs|rb|php|sh|zsh|bash|sql|lua|vim|el|R|jl|m|mm|gradle|cmake|dockerfile|makefile|gitignore|editorconfig)$'

# 排除目录名（任一段路径匹配即跳过）
EXCLUDE_DIRS_RE='/(\.git|node_modules|\.venv|venv|env|\.env|__pycache__|\.pytest_cache|\.mypy_cache|\.ruff_cache|\.next|\.nuxt|\.svelte-kit|\.turbo|dist|build|out|target|\.gradle|\.idea|\.vscode|\.vs|\.DS_Store|Library|\.cache|\.npm|\.yarn|\.pnpm-store|\.bun|\.cargo|\.rustup|\.local|\.Trash|Trash|node_modules|bower_components|vendor|coverage|\.terraform|\.serverless|tmp|\.tmp|logs|\.log|\.parcel-cache|\.docusaurus|\.expo|Pods|DerivedData|xcuserdata|\.tox|site-packages)/'

# 敏感文件名 pattern
SENSITIVE_RE='(\.key$|\.pem$|\.p12$|\.pfx$|\.env(\..*)?$|^\.env|id_rsa|id_ed25519|credentials|secrets?\.|\.aws/|\.ssh/|\.gnupg/|\.kube/|\.docker/config|password)'

> "$OUT_TSV"
> "$OUT_SUM"
echo "[scan] 开始扫描白名单..." >&2

count=0
# shellcheck disable=SC2013
while IFS= read -r line; do
  # 跳过空行/注释
  line="${line%%#*}"
  line="$(echo -n "$line" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
  [ -z "$line" ] && continue
  # 展开 ~
  root="${line/#\~/$HOME}"
  [ ! -d "$root" ] && { echo "[skip] 不存在: $root" >&2; continue; }
  echo "[scan] 扫描根目录: $root" >&2

  # find: 列出文件 (printf size mtime path) 然后过滤
  find "$root" -type f -size -2M 2>/dev/null \
    | grep -Ev "$EXCLUDE_DIRS_RE" \
    | grep -Ei "$EXTS_RE" \
    | grep -Eiv "$SENSITIVE_RE" \
    | while IFS= read -r f; do
        sz=$(stat -f%z "$f" 2>/dev/null || echo 0)
        mt=$(stat -f%m "$f" 2>/dev/null || echo 0)
        printf "%s\t%s\t%s\n" "$sz" "$mt" "$f"
      done >> "$OUT_TSV"
done < "$SOURCES"

count=$(wc -l < "$OUT_TSV" | tr -d ' ')
echo "[scan] 收录候选文件: $count" >&2

# 统计
{
  echo "# 知识源扫描报告 - $(date)"
  echo
  echo "## 总计"
  echo "- 候选文件数: $count"
  echo "- 总大小: $(awk -F'\t' '{s+=$1} END{printf "%.1f MB\n", s/1024/1024}' "$OUT_TSV")"
  echo
  echo "## Top 20 扩展名"
  awk -F'\t' '{n=split($3,a,"."); print tolower(a[n])}' "$OUT_TSV" | sort | uniq -c | sort -rn | head -20
  echo
  echo "## Top 20 一级目录"
  awk -F'\t' -v home="$HOME" '{p=$3; sub(home"/","",p); n=split(p,a,"/"); print a[1]"/"a[2]}' "$OUT_TSV" | sort | uniq -c | sort -rn | head -20
} > "$OUT_SUM"

echo "[scan] 完成。摘要：$OUT_SUM"
echo "[scan] 文件清单：$OUT_TSV"
