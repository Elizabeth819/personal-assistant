"""WebDriverAgent HTTP client — drives a USB-tethered iPhone via tap/type/swipe.

Requires:
  - WDA runner installed on device (com.wanmeng.WebDriverAgentRunner)
  - `xcodebuild test-without-building` running in background to host the WDA HTTP server
  - `iproxy 8100 8100 -u <udid>` forwarding device:8100 → mac:8100

Then this module talks plain HTTP to http://127.0.0.1:8100.
"""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

from pa.core import get_logger

log = get_logger(__name__)


WDA_BASE = "http://127.0.0.1:8100"
_session_id: str | None = None


def _clean_json(text: str) -> Any:
    """WDA sometimes returns control chars in tracebacks — strip before parsing."""
    cleaned = re.sub(r"[\x00-\x08\x0b-\x1f]", " ", text)
    return json.loads(cleaned)


async def _ensure_session(bundle_id: str | None = None) -> str:
    global _session_id
    async with httpx.AsyncClient(timeout=30) as c:
        if _session_id:
            r = await c.get(f"{WDA_BASE}/session/{_session_id}")
            if r.status_code == 200:
                return _session_id
        caps: dict[str, Any] = {}
        if bundle_id:
            caps["bundleId"] = bundle_id
        r = await c.post(
            f"{WDA_BASE}/session",
            json={"capabilities": {"alwaysMatch": caps}},
        )
        r.raise_for_status()
        data = _clean_json(r.text)
        _session_id = data["value"]["sessionId"]
        return _session_id  # type: ignore[return-value]


async def status() -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(f"{WDA_BASE}/status")
        r.raise_for_status()
        return _clean_json(r.text)


async def activate_app(bundle_id: str) -> dict[str, Any]:
    sid = await _ensure_session(bundle_id)
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(
            f"{WDA_BASE}/session/{sid}/wda/apps/launch",
            json={"bundleId": bundle_id},
        )
        return {"ok": r.status_code == 200, "raw": r.text[:200]}


async def page_source() -> str:
    sid = await _ensure_session()
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(f"{WDA_BASE}/session/{sid}/source")
        r.raise_for_status()
        return _clean_json(r.text)["value"]  # type: ignore[no-any-return]


async def find_element(strategy: str, value: str) -> str | None:
    sid = await _ensure_session()
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(
            f"{WDA_BASE}/session/{sid}/element",
            json={"using": strategy, "value": value},
        )
        if r.status_code != 200:
            return None
        d = _clean_json(r.text).get("value", {})
        if isinstance(d, dict):
            return d.get("ELEMENT") or d.get("element-6066-11e4-a52e-4f735466cecf")
    return None


async def find_by_text(text: str) -> str | None:
    """Try several strategies to locate a tappable element by user-visible text."""
    for strategy, val in [
        ("accessibility id", text),
        ("name", text),
        ("predicate string", f"label == '{text}' OR name == '{text}' OR value == '{text}'"),
        ("predicate string", f"label CONTAINS '{text}' OR name CONTAINS '{text}'"),
    ]:
        eid = await find_element(strategy, val)
        if eid:
            return eid
    return None


async def tap_element(element_id: str) -> dict[str, Any]:
    sid = await _ensure_session()
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(
            f"{WDA_BASE}/session/{sid}/element/{element_id}/click",
            json={},
        )
        return {"ok": r.status_code == 200, "raw": r.text[:200]}


async def find_xy_in_source(text: str) -> tuple[int, int] | None:
    """Fallback: regex the page source for name/label==text and return its center."""
    try:
        src = await page_source()
    except Exception:
        return None
    pat = re.compile(
        r'(?:name|label|value)="' + re.escape(text) + r'"[^>]*?'
        r'x="(-?\d+)"\s+y="(-?\d+)"\s+width="(\d+)"\s+height="(\d+)"'
    )
    m = pat.search(src)
    if not m:
        pat2 = re.compile(
            r'x="(-?\d+)"\s+y="(-?\d+)"\s+width="(\d+)"\s+height="(\d+)"[^>]*?'
            r'(?:name|label|value)="' + re.escape(text) + r'"'
        )
        m = pat2.search(src)
    if not m:
        return None
    x, y, w, h = (int(m.group(i)) for i in (1, 2, 3, 4))
    return x + w // 2, y + h // 2


async def tap_text(text: str) -> dict[str, Any]:
    eid = await find_by_text(text)
    if eid:
        res = await tap_element(eid)
        return {"action": "tap_text", "text": text, "ok": res["ok"], "element": eid}
    xy = await find_xy_in_source(text)
    if xy:
        res = await tap_xy(xy[0], xy[1])
        return {"action": "tap_text", "text": text, "ok": res["ok"], "via": "xy", "xy": xy}
    return {"action": "tap_text", "text": text, "ok": False, "error": "not found"}


async def tap_xy(x: int, y: int) -> dict[str, Any]:
    """Tap absolute coordinates via W3C actions API."""
    sid = await _ensure_session()
    body = {
        "actions": [
            {
                "type": "pointer",
                "id": "finger1",
                "parameters": {"pointerType": "touch"},
                "actions": [
                    {"type": "pointerMove", "duration": 0, "x": x, "y": y},
                    {"type": "pointerDown", "button": 0},
                    {"type": "pause", "duration": 50},
                    {"type": "pointerUp", "button": 0},
                ],
            }
        ]
    }
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(f"{WDA_BASE}/session/{sid}/actions", json=body)
        return {"action": "tap_xy", "x": x, "y": y, "ok": r.status_code == 200, "raw": r.text[:200]}


async def type_text(text: str) -> dict[str, Any]:
    sid = await _ensure_session()
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(
            f"{WDA_BASE}/session/{sid}/wda/keys",
            json={"value": list(text)},
        )
        return {"action": "type_text", "ok": r.status_code == 200, "raw": r.text[:200]}


async def swipe(direction: str = "up") -> dict[str, Any]:
    sid = await _ensure_session()
    async with httpx.AsyncClient(timeout=30) as c:
        # window dimensions
        r = await c.get(f"{WDA_BASE}/session/{sid}/window/size")
        sz = _clean_json(r.text)["value"]
        w, h = int(sz["width"]), int(sz["height"])
        midx = w // 2
        if direction == "up":
            from_y, to_y = int(h * 0.75), int(h * 0.25)
        else:
            from_y, to_y = int(h * 0.25), int(h * 0.75)
        body = {
            "actions": [
                {
                    "type": "pointer",
                    "id": "f",
                    "parameters": {"pointerType": "touch"},
                    "actions": [
                        {"type": "pointerMove", "duration": 0, "x": midx, "y": from_y},
                        {"type": "pointerDown", "button": 0},
                        {"type": "pointerMove", "duration": 300, "x": midx, "y": to_y},
                        {"type": "pointerUp", "button": 0},
                    ],
                }
            ]
        }
        r = await c.post(f"{WDA_BASE}/session/{sid}/actions", json=body)
        return {"action": "swipe", "direction": direction, "ok": r.status_code == 200}


async def screenshot_b64() -> str | None:
    sid = await _ensure_session()
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(f"{WDA_BASE}/session/{sid}/screenshot")
        if r.status_code != 200:
            return None
        return _clean_json(r.text).get("value")  # type: ignore[no-any-return]


async def open_url(url: str) -> dict[str, Any]:
    """Open any URL/deeplink on the device via Safari's URL endpoint.

    iOS routes registered URL schemes to the owning app, so this also
    triggers `tel://`, `weixin://`, `taobao://`, etc.
    Activate Safari first so the URL handoff works regardless of the
    previous WDA-session foreground app.
    """
    try:
        await activate_app("com.apple.mobilesafari")
    except Exception:
        pass
    sid = await _ensure_session("com.apple.mobilesafari")
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(
            f"{WDA_BASE}/session/{sid}/url",
            json={"url": url},
        )
        return {"action": "open_url", "url": url, "ok": r.status_code == 200, "raw": r.text[:200]}


async def screen_explain(instruction: str) -> dict[str, Any]:
    """Snap the screen and ask GPT-4 vision to describe it."""
    b64 = await screenshot_b64()
    if not b64:
        return {"action": "screen_explain", "ok": False, "error": "screenshot failed"}
    try:
        from pa.voice.azure_openai import describe_image
        text = await describe_image(b64, instruction)
        return {"action": "screen_explain", "ok": True, "text": text}
    except Exception as exc:
        log.exception("screen_explain.failed")
        return {"action": "screen_explain", "ok": False, "error": str(exc)}


async def execute(action: dict[str, Any]) -> dict[str, Any]:
    t = action.get("type")
    try:
        if t == "tap_text":
            bundle = action.get("bundle_id")
            if bundle:
                await activate_app(bundle)
            return await tap_text(action["text"])
        if t == "tap_xy":
            return await tap_xy(int(action["x"]), int(action["y"]))
        if t == "type_text":
            return await type_text(action["text"])
        if t == "swipe":
            return await swipe(action.get("direction", "up"))
        if t == "activate_app":
            return await activate_app(action["bundle_id"])
        if t == "open_url":
            return await open_url(action["url"])
        if t == "screen_explain":
            return await screen_explain(action.get("instruction", "描述屏幕内容"))
    except Exception as exc:
        log.exception("wda.execute_failed", action=action)
        return {"action": t, "ok": False, "error": str(exc)}
    return {"action": t, "ok": False, "error": "unknown wda action"}
