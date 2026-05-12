"""Drive a USB-tethered iPhone via Apple's `devicectl`.

Capabilities (no jailbreak, no WDA, just CoreDevice):
- launch any installed app by bundle id  → `open_app`
- list installed apps

Things `devicectl` CANNOT do (handed to the iPhone-side Shortcut over HTTP):
- open URL / deep link (argv is ignored by iOS URL handlers)
- tap buttons, type, scroll  (would need WDA/Appium)
"""

from __future__ import annotations

import asyncio
import shlex
from typing import Any

from pa.core import get_logger

log = get_logger(__name__)


BUNDLE_IDS: dict[str, str] = {
    # Tencent
    "微信": "com.tencent.xin",
    "wechat": "com.tencent.xin",
    "qq": "com.tencent.mqq",
    "qq邮箱": "com.tencent.qqmail",
    "微信读书": "com.tencent.weread",
    # Alibaba
    "支付宝": "com.alipay.iphoneclient",
    "alipay": "com.alipay.iphoneclient",
    "淘宝": "com.taobao.taobao4iphone",
    "闲鱼": "com.taobao.fleamarket",
    # Maps & travel
    "高德": "com.autonavi.amap",
    "高德地图": "com.autonavi.amap",
    "amap": "com.autonavi.amap",
    "百度地图": "com.baidu.map",
    "google maps": "com.google.Maps",
    "苹果地图": "com.apple.Maps",
    "地图": "com.apple.Maps",
    "maps": "com.apple.Maps",
    "12306": "cn.12306.rails12306",
    "携程": "ctrip.com",
    "携程旅行": "ctrip.com",
    "去哪儿": "com.qunar.iphoneclient8",
    # O2O
    "美团": "com.meituan.imeituan",
    "饿了么": "me.ele.ios.eleme",
    "滴滴": "com.xiaojukeji.didi",
    "didi": "com.xiaojukeji.didi",
    # E-commerce
    "京东": "com.360buy.jdmobile",
    "拼多多": "com.xunmeng.pinduoduo",
    # Music
    "网易云": "com.netease.cloudmusic",
    "网易云音乐": "com.netease.cloudmusic",
    "汽水音乐": "com.soda.music",
    "spotify": "com.spotify.client",
    "music": "com.apple.Music",
    "apple music": "com.apple.Music",
    "音乐": "com.apple.Music",
    # Video / social
    "抖音": "com.ss.iphone.ugc.Aweme",
    "tiktok": "com.ss.iphone.ugc.Aweme",
    "bilibili": "tv.danmaku.bilianime",
    "哔哩哔哩": "tv.danmaku.bilianime",
    "youtube": "com.google.ios.youtube",
    "今日头条": "com.ss.iphone.article.News",
    "知乎": "com.zhihu.ios",
    "小红书": "com.xingin.discover",
    "rednote": "com.xingin.discover",
    # IM
    "facebook": "com.facebook.Facebook",
    "telegram": "ph.telegra.Telegraph",
    "whatsapp": "net.whatsapp.WhatsApp",
    "discord": "com.hammerandchisel.discord",
    # Apple defaults
    "safari": "com.apple.mobilesafari",
    "日历": "com.apple.mobilecal",
    "calendar": "com.apple.mobilecal",
    "备忘录": "com.apple.mobilenotes",
    "notes": "com.apple.mobilenotes",
    "shortcuts": "com.apple.shortcuts",
    "快捷指令": "com.apple.shortcuts",
    "计算器": "com.apple.calculator",
    "calculator": "com.apple.calculator",
    "邮件": "com.apple.mobilemail",
    "mail": "com.apple.mobilemail",
    "keep": "com.gotokeep.keep",
    # Mail
    "gmail": "com.google.Gmail",
    "outlook": "com.microsoft.Office.Outlook",
    # Misc
    "豆包": "com.bot.doubao",
    "百度网盘": "com.baidu.netdisk",
}


async def _run(cmd: list[str], timeout: float = 30.0) -> tuple[int, str, str]:
    log.info("devicectl.run", cmd=" ".join(shlex.quote(c) for c in cmd))
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        proc.kill()
        return 124, "", "timeout"
    return proc.returncode or 0, stdout.decode("utf-8", "replace"), stderr.decode("utf-8", "replace")


def resolve_bundle(name: str) -> str:
    return BUNDLE_IDS.get(name.strip().lower(), name)


async def list_devices() -> list[dict[str, Any]]:
    code, _out, _err = await _run(["xcrun", "devicectl", "list", "devices", "--json-output", "/tmp/_devs.json"])
    if code != 0:
        return []
    import json
    from pathlib import Path
    data = json.loads(Path("/tmp/_devs.json").read_text())
    items = data.get("result", {}).get("devices", [])
    return [
        {
            "udid": d.get("hardwareProperties", {}).get("udid"),
            "identifier": d.get("identifier"),
            "name": d.get("deviceProperties", {}).get("name"),
            "platform": d.get("hardwareProperties", {}).get("platform"),
        }
        for d in items
    ]


async def open_app(device_udid: str, app: str) -> dict[str, Any]:
    bundle = resolve_bundle(app)
    code, out, err = await _run(
        ["xcrun", "devicectl", "device", "process", "launch",
         "--device", device_udid, bundle]
    )
    return {
        "action": "open_app", "app": app, "bundle": bundle, "ok": code == 0,
        "stdout": out.strip()[-200:], "stderr": err.strip()[-200:],
    }


async def execute(device_udid: str, action: dict[str, Any]) -> dict[str, Any]:
    """Execute one planned action on the tethered device.

    Handles `open_app` directly via devicectl. WDA-class actions
    (tap_text/tap_xy/type_text/swipe/open_url/screen_explain) are delegated.
    `weather` is a network query — handled inline.
    """
    t = action.get("type")
    if t == "open_app":
        return await open_app(device_udid, action["app"])
    if t in {"tap_text", "tap_xy", "type_text", "swipe", "open_url", "screen_explain"}:
        from pa.adapters import ios_wda
        return await ios_wda.execute(action)
    if t == "weather":
        from pa.adapters import weather as wx
        return await wx.execute(action)
    if t == "say":
        return {"action": "say", "skipped": True}
    return {"action": t, "deferred": True}


async def run_actions(device_udid: str, actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [await execute(device_udid, a) for a in actions]
