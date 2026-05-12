# 喂给 Claude 的标准 prompt（每批使用）

把下面这段复制到 `claude` 会话里，并把 `BATCH_FILE` 换成具体批次路径。
claude-mem 的 PostToolUse hook 会自动把模型生成的"事实/经历/知识点"写入 memory。

---

我要把我个人电脑上的知识/经历批量存入你的长期记忆（claude-mem）。

请按下面的 SOP 处理 BATCH_FILE 里列出的文件：

【BATCH_FILE】= ~/repository/personal-assistant/manifests/batch_0000.txt

SOP：
1. 读取 BATCH_FILE，得到一组绝对路径。
2. 对每个文件：
   - 用 Read 工具读全文（PDF 用 `pdftotext` 转纯文本，ipynb 只看 markdown+代码）
   - 跳过明显的：自动生成代码、第三方库源码、压缩/二进制
   - 提取以下 5 类信息（缺则跳过）：
     a. **个人经历**（事件、时间、地点、人、感受）
     b. **学到的知识点**（概念、公式、命令、API、模式）
     c. **决定与偏好**（我选了什么/为什么、规范、习惯）
     d. **未完成项**（TODO、想做但没做的事）
     e. **重要资源**（链接、引用、值得回看的文件路径）
3. 每个文件输出一段 **结构化摘要**，格式：
   ```
   ### <相对路径>
   - 类型: 笔记/代码/文档/...
   - 摘要: <2-3 句>
   - 经历: ...
   - 知识点: ...
   - 决定/偏好: ...
   - TODO: ...
   - 资源: ...
   ```
4. 处理完整批后，**显式声明：「请将以上内容存入长期记忆，按主题打 tag（如 #project/xxx #skill/yyy #person/zzz）」**——这一步会触发 claude-mem 的 observation hook 入库。
5. 最后把这一批的"主题清单 + 文件计数"追加写入 `~/repository/personal-assistant/logs/ingest.log`。

注意：
- 不要把整个文件原文复述出来，只摘要。
- 遇到密码/密钥/token 立即跳过并标记 [SENSITIVE-SKIPPED]。
- 每批控制在 30 分钟内完成，超时就停下来给我汇总。

开始吧。
