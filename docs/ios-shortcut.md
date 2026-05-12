# iOS 快捷指令 → personal-assistant 闭环（带动作 dispatch）

## 后端契约

### 入口

`POST /voice/turn`（multipart）
- `audio`：录音文件（m4a 即可）
- `system`（可选）：覆盖系统提示词
- `audio_format`（可选）：`b64`（默认，JSON 内含合成 wav 的 base64）/ `binary`（直接返 wav，旧行为）/ `none`（不合成）

`POST /voice/text`（multipart，跳过 ASR，调试用）
- `text`：用户文字
- `with_audio`（默认 false）

### 响应（JSON 模式）

```json
{
  "user_text": "放周杰伦的晴天",
  "reply_text": "好的，正在为你播放 ...",
  "actions": [
    {"type": "play_music", "query": "周杰伦 晴天"},
    {"type": "say", "text": "好的，正在为你播放 ..."}
  ],
  "audio_wav_b64": "UklGR..."
}
```

### 当前 action 类型

| type | 字段 | iOS 动作 |
|---|---|---|
| `say` | `text` | 朗读 / 通知 |
| `play_music` | `query` | 在 Music / Apple Music 里搜索播放 |
| `open_app` | `app` | "打开 App" |
| `open_url` | `url` | "打开 URL" |
| `set_timer` | `seconds`, `label` | "开始计时器" |
| `navigate` | `destination` | "在地图中显示" |

## iPhone 端"Talk PA"快捷指令骨架

按顺序加这些 Action（中文版动作名，英文版在括号里）：

1. **录制音频**（Record Audio）
   - 停止录音：按"完成"
2. **获取 URL 内容**（Get Contents of URL）
   - URL：`https://<你的 tunnel>.trycloudflare.com/voice/turn`
   - 方法：POST
   - 请求体：表单
     - `audio` = 文件 = "录制的音频"
     - `audio_format` = 文本 = `b64`
3. **从输入获取词典**（Get Dictionary from Input）—— 把 JSON 解析成字典
4. **获取词典值**（Get Dictionary Value）：键 `audio_wav_b64`，存为变量 `AudioB64`
5. **Base64 编码**（Base64 Encode，模式选 Decode）输入 `AudioB64`，存为 `AudioFile`
6. **播放声音**（Play Sound）输入 `AudioFile`
7. **获取词典值**：键 `actions`，存为变量 `Actions`
8. **重复每一项**（Repeat with Each）输入 `Actions`：
   - 内部：**获取词典值** 键 `type`，存为 `T`
   - **如果**（If）`T` 等于 `play_music`：
     - 取 `query`，**搜索 Apple Music**（Search Music），取第一个结果，**播放音乐**
   - **否则如果** `T` = `open_app`：取 `app`，**打开 App**
   - **否则如果** `T` = `open_url`：取 `url`，**打开 URL**
   - **否则如果** `T` = `set_timer`：取 `seconds`、`label`，**开始计时器**
   - **否则如果** `T` = `navigate`：取 `destination`，**在地图中显示**
   - **否则如果** `T` = `say`：跳过（步骤 6 已经播了 TTS）

存成快捷指令，加到主屏 / 添加到 Siri "嘿小助理"。

## 用例验证

```bash
# 文本入口快速验
curl -s -X POST http://127.0.0.1:8771/voice/text \
  -F text="放周杰伦的晴天" | python3 -m json.tool

curl -s -X POST http://127.0.0.1:8771/voice/text \
  -F text="10分钟后提醒我喝水" | python3 -m json.tool

# 完整音频回路
say -o /tmp/q.aiff "打开微信"
afconvert -f mp4f -d aac /tmp/q.aiff /tmp/q.m4a
curl -s -X POST http://127.0.0.1:8771/voice/turn \
  -F "audio=@/tmp/q.m4a;type=audio/mp4" \
  -F "audio_format=none" | python3 -m json.tool
```

## 当前隧道地址

```
https://contributed-balance-act-including.trycloudflare.com
```

quick tunnel 重启会换，要长稳就升级 named tunnel + 自有域名。

## 局限

- planner 是规则匹配，覆盖不了瑞幸点单这种深 GUI；那条要 Mac 镜像 + Appium，下一阶段做
- 没鉴权，公网可调用 → 加 Bearer token
- `play_music` 只能在 Apple Music 有版权时播；网易云得改成 `open_url` + 搜索 deep link
