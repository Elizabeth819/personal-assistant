"""Lightweight rule-based intent → iOS-action planner.

Returns a list of action dicts the iOS Shortcut can dispatch on:
  {"type": "open_app",      "app": "微信"}
  {"type": "play_music",    "query": "周杰伦 晴天"}
  {"type": "set_timer",     "seconds": 600, "label": "煮面"}
  {"type": "open_url",      "url": "https://..."}
  {"type": "send_message",  "to": "...", "body": "..."}
  {"type": "navigate",      "destination": "天安门"}
  {"type": "say",           "text": "..."}   # fallback: just speak the reply
"""

from __future__ import annotations

import re
from typing import Any

from pa.adapters.ios_devicectl import BUNDLE_IDS as _APP_ALIASES_RAW

Action = dict[str, Any]

_TIMER_UNIT_SECONDS = {
    "秒": 1,
    "second": 1,
    "seconds": 1,
    "分": 60,
    "分钟": 60,
    "minute": 60,
    "minutes": 60,
    "小时": 3600,
    "hour": 3600,
    "hours": 3600,
}

# Reverse-map every known alias → its canonical Chinese display name we'll
# pass downstream as `app`. The adapter resolves it back to a bundle id.
_APP_ALIASES = dict(_APP_ALIASES_RAW)


# (alias-pattern, deeplink template, human-readable app name)
# `{q}` will be url-encoded query.
_SEARCH_DEEPLINKS: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"(淘宝)", re.I), "taobao://s.taobao.com/?q={q}", "淘宝"),
    (re.compile(r"(京东)", re.I), "openjd://virtual?params=%7B%22sourceValue%22%3A%22{q}%22%2C%22category%22%3A%22jump%22%2C%22des%22%3A%22productList%22%2C%22keyWord%22%3A%22{q}%22%7D", "京东"),
    (re.compile(r"(小红书|rednote|xhs)", re.I), "xhsdiscover://search/result?keyword={q}", "小红书"),
    (re.compile(r"(高德|amap|地图)", re.I), "iosamap://poi?sourceApplication=pa&keywords={q}&dev=0", "高德"),
    (re.compile(r"(百度地图)", re.I), "baidumap://map/place/search?query={q}&src=ios.pa", "百度地图"),
    (re.compile(r"(b站|bilibili|哔哩)", re.I), "bilibili://search?keyword={q}", "B站"),
    (re.compile(r"(知乎)", re.I), "zhihu://search?q={q}&type=general", "知乎"),
    (re.compile(r"(抖音|tiktok)", re.I), "snssdk1128://search/trending?keyword={q}", "抖音"),
    (re.compile(r"(美团)", re.I), "imeituan://www.meituan.com/search?q={q}", "美团"),
    (re.compile(r"(饿了么)", re.I), "eleme://search?keyword={q}", "饿了么"),
    (re.compile(r"(youtube)", re.I), "youtube://results?search_query={q}", "YouTube"),
    (re.compile(r"(网易云)", re.I), "orpheus://search/{q}", "网易云"),
    (re.compile(r"(spotify)", re.I), "spotify:search:{q}", "Spotify"),
    (re.compile(r"(apple\s*music|苹果音乐|音乐)", re.I), "music://music.apple.com/search?term={q}", "Apple Music"),
    (re.compile(r"(12306|火车票|高铁)", re.I), "https://kyfw.12306.cn/otn/leftTicket/init?{q}", "12306"),
]


def _parse_search(text: str) -> Action | None:
    """e.g. '淘宝搜耳机', '在京东搜AirPods', '小红书查上海周末去哪玩', 'youtube 搜 lofi'"""
    # also: '<app>里搜<q>' / '<app>看<q>' / '<app>搜索<q>'
    m = re.search(
        r"(?:在|去|用)?\s*(\S{1,8}?)\s*(?:里|上|中)?\s*(?:搜|搜索|查|查询|找|找找)\s*(.+?)$",
        text,
    )
    if not m:
        return None
    app_token, q = m.group(1).strip(), m.group(2).strip().rstrip("。.,，?? ")
    if not q:
        return None
    from urllib.parse import quote
    qenc = quote(q)
    for pat, tpl, _name in _SEARCH_DEEPLINKS:
        if pat.search(app_token):
            return {"type": "open_url", "url": tpl.format(q=qenc)}
    return None


def _parse_dial(text: str) -> Action | None:
    """e.g. '打电话给 13800138000', '拨打 110', 'call 911'"""
    m = re.search(r"(?:打电话给|拨打?|呼叫|call|dial)\s*([\+\d\-\s]{3,20})", text, re.I)
    if not m:
        return None
    num = re.sub(r"[^\d+]", "", m.group(1))
    if not num:
        return None
    return {"type": "open_url", "url": f"tel://{num}"}


def _parse_weather(text: str) -> Action | None:
    """e.g. '上海明天会下雨吗', '北京周末天气怎么样', '查一下北京天气'"""
    # explicit interrogative or query verb required — avoids matching '今天天气不错'
    if not re.search(r"会下雨|多少度|气温|温度|怎么样|如何|查.{0,3}天气|看.{0,3}天气|forecast", text, re.I):
        # also accept 'X 天气吗?' or '天气?' style
        if not re.search(r"天气[?？吗]", text):
            return None
    if re.search(r"天气(?:不错|真好|挺好|很好|很糟)", text):
        return None
    m = re.search(r"(?:在?|的)?([^\s，。,.?]{2,8}?)(?:今天|明天|后天|周末|本周|这周)?\s*(?:天气|会下雨|温度|气温|多少度|weather)", text)
    city = (m.group(1).strip() if m else "").rstrip("的")
    when = "today"
    if "明天" in text:
        when = "tomorrow"
    elif "后天" in text:
        when = "+2d"
    elif "周末" in text or "本周" in text or "这周" in text:
        when = "week"
    return {"type": "weather", "city": city or "current", "when": when}


def _parse_screen_explain(text: str) -> Action | None:
    """e.g. '看看屏幕', '帮我看看现在屏幕上是什么', '截屏解释一下', '翻译一下屏幕上的英文'"""
    if re.search(r"(看看屏幕|看一下屏幕|屏幕上是什么|截屏看|帮我看屏幕|解释一下屏幕|翻译.*屏幕|屏幕.*翻译)", text):
        instruction = "用一两句中文说屏幕里在显示什么、能做什么操作。"
        if "翻译" in text:
            instruction = "把屏幕里的非中文内容翻译成中文,简短。"
        return {"type": "screen_explain", "instruction": instruction}
    return None



def _parse_timer(text: str) -> Action | None:
    m = re.search(r"(\d+)\s*(秒|分钟|分|小时|seconds?|minutes?|hours?)", text, re.IGNORECASE)
    if not m:
        return None
    n = int(m.group(1))
    unit = m.group(2).lower()
    seconds = n * _TIMER_UNIT_SECONDS.get(unit, 60)
    label_match = re.search(r"提醒我\s*(.+?)(?:$|[。,，])", text)  # noqa: RUF001
    label = label_match.group(1).strip() if label_match else "计时器"
    return {"type": "set_timer", "seconds": seconds, "label": label}


def _parse_play_music(text: str) -> Action | None:
    if not re.search(r"(放|播放|来一首|听|play)", text, re.IGNORECASE):
        return None
    q = re.sub(r".*?(放|播放|来一首|听|play)\s*", "", text, count=1, flags=re.IGNORECASE)
    q = re.sub(r"(的歌|歌|音乐|吧|呗|please)$", "", q.strip(), flags=re.IGNORECASE).strip()
    return {"type": "play_music", "query": q or "随机"}


def _parse_open_app(text: str) -> Action | None:
    low = text.lower()
    if not re.search(r"(打开|启动|open|launch|进入|跳转)", low):
        return None
    # longest alias first → 'apple music' wins over 'music'
    for alias in sorted(_APP_ALIASES.keys(), key=len, reverse=True):
        if alias in low:
            return {"type": "open_app", "app": alias}
    return None


def _parse_navigate(text: str) -> Action | None:
    m = re.search(r"(?:导航到|去|带我去|navigate to)\s*(.+?)(?:$|[。,，])", text)  # noqa: RUF001
    if not m:
        return None
    return {"type": "navigate", "destination": m.group(1).strip()}


def _parse_url(text: str) -> Action | None:
    m = re.search(r"https?://\S+", text)
    return {"type": "open_url", "url": m.group(0)} if m else None


def _parse_tap(text: str) -> Action | None:
    m = re.search(r"(?:点击|点一下|点按|点开|tap|click)\s*(.+?)(?:$|[。,，])", text)  # noqa: RUF001
    if m:
        return {"type": "tap_text", "text": m.group(1).strip()}
    return None


def _parse_type(text: str) -> Action | None:
    m = re.search(r"(?:输入|键入|type|enter)\s*[:：]?\s*(.+?)(?:$|[。,，])", text)  # noqa: RUF001
    if m:
        return {"type": "type_text", "text": m.group(1).strip()}
    return None


def _parse_swipe(text: str) -> Action | None:
    if re.search(r"(往下滑|向下滑|下拉|swipe down)", text):
        return {"type": "swipe", "direction": "down"}
    if re.search(r"(往上滑|向上滑|上滑|滑动|swipe up|swipe)", text):
        return {"type": "swipe", "direction": "up"}
    return None


def _parse_react(text: str) -> Action | None:
    """Route open-ended multi-step phone tasks to the visual ReAct loop.

    Triggers:
      - explicit '帮我...' / '替我...' / '自动...' phrasing with a phone-side verb
      - explicit '使用 react / react agent' marker
    """
    if re.search(r"(?:react\s*(?:agent|模式)?|自动操作|帮我操作|替我操作|帮我点|替我点|自动完成)", text, re.I):
        return {"type": "react", "goal": text.strip()}
    if re.search(r"(帮我|替我|麻烦你)\s*(?:去|把|将|完成|搞定|处理|退|订|买|发|回复|清理)", text):
        return {"type": "react", "goal": text.strip()}
    return None


def plan_actions(user_text: str, reply_text: str) -> list[Action]:
    """Return a list of iOS-dispatchable actions inferred from the user intent.

    Splits compound utterances on common conjunctions (然后/再/接着/and then/,)
    so "打开高德然后导航到天安门" yields both open_app and navigate.
    The reply text is always spoken last.
    """
    parsers = (
        _parse_react,
        _parse_screen_explain,
        _parse_weather,
        _parse_dial,
        _parse_search,
        _parse_tap,
        _parse_type,
        _parse_swipe,
        _parse_timer,
        _parse_play_music,
        _parse_open_app,
        _parse_navigate,
        _parse_url,
    )
    chunks = re.split(r"(?:然后|再|接着|，然后|, then|; |。)", user_text)
    actions: list[Action] = []
    seen: set[str] = set()
    last_app: str | None = None
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        for p in parsers:
            a = p(chunk)
            if not a and p is _parse_search and last_app:
                # chain context: 前面打开了某 app, 这一段是孤零零的 "搜X" — 给它补上 app 名
                a = _parse_search(f"{last_app}{chunk}")
            if not a:
                continue
            if a.get("type") == "open_app":
                last_app = a.get("app")
            key = f"{a.get('type')}:{a.get('app') or a.get('url') or a.get('text') or a.get('destination') or a.get('city') or a.get('seconds') or a.get('query') or ''}"
            if key in seen:
                continue
            seen.add(key)
            actions.append(a)
            break
    actions.append({"type": "say", "text": reply_text})
    return actions
