# personal-assistant

## 项目目标

打造一个**属于"我"的个人助理** —— 一个知道我是谁、记得我做过什么、了解我偏好和习惯的 AI 助理。

这个仓库是整个个人助理建设的**起点**，而不是终点。

### 路线图

1. **第一步（当前阶段）：灌输记忆** ← 我们现在在这里
   把本机上的笔记、代码、文档、聊天、邮件等批量喂给 claude-mem，让助理拥有"我过去的全部"作为长期记忆底座。
2. **第二步：持续同步** — 把日常新产生的信息（新文件、新对话、新决定）增量进记忆。
3. **第三步：能力扩展** — 在记忆之上接入日历、邮件、任务、搜索等工具，让助理能代我行动。
4. **第四步：主动性** — 助理基于记忆主动提醒、归纳、建议，而不是被动回答。

**本仓库的所有脚本目前都服务于"第一步"。**不要把这里的工具当作目的本身，它们是给个人助理"装灵魂"的灌输管道。

## 当前阶段（记忆灌输）的工作流

- `ingest/sources.txt` — 扫描白名单（每行一个根目录）
- `ingest/scan.sh` — 扫白名单，产出 `manifests/files.tsv` 和 `summary.txt`
- `ingest/batch.sh N` — 把 files.tsv 按 N 个一批切成 `manifests/batch_XXXX.txt`
- `ingest/run_batch.sh START END` — headless 调 claude 处理 batch_START..batch_END
- `ingest/PROMPT_TEMPLATE.md` — 每批的 SOP（提取 5 类：经历 / 知识 / 偏好 / TODO / 资源）
- `logs/batch_XXXX.log` — 每批的 headless 输出
- `snapshots/` — claude-mem 数据备份
- `manifests/` — 扫描结果与切好的批次清单

```bash
$EDITOR ingest/sources.txt          # 1. 编辑白名单
./ingest/scan.sh                    # 2. 扫描
./ingest/batch.sh 50                # 3. 切批
./ingest/run_batch.sh 0 9           # 4. 自动批量（需 copilot-api :4142）
```

## 依赖与外部服务

- `claude` CLI（绝对路径 `/usr/local/bin/claude`，因为 zsh 里它是函数）
- `copilot-api` 监听 :4142，`run_batch.sh` 会自动拉起
- claude-mem observations UI: http://localhost:37701
- claude-mem 的 PostToolUse hook 会把模型输出的结构化摘要写进 memory —— **prompt 输出格式不能随便改**，改了就不入库
- memory 实际落库位置：`~/.claude/plugins/data/claude-mem-thedotmack`

## 注意事项

- `scan.sh` 已排除 *.key / *.pem / *.env / id_rsa 与缓存目录，但跑大批前仍建议 `head manifests/files.tsv` 抽查
- 涉及他人隐私（聊天 / 合同 / 邮件）的目录单独白名单管理，**不要和主 sources.txt 混用**
- 备份：`tar -czf snapshots/claude-mem-$(date +%Y%m%d).tgz -C ~/.claude/plugins/data claude-mem-thedotmack`
- `run_batch.sh` 使用 `--dangerously-skip-permissions`，仅限本项目 headless 灌库场景
