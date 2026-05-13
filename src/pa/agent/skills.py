"""Declarative skill registry — named per-app capabilities the LLM can call.

Each Skill is a recipe: (name, app, arg names, action sequence template).
At call time we substitute args and dispatch the actions through ios_wda.

This is the "tool" layer the planner/voice loop selects from when a user
intent maps to a known recurring app workflow (search Taobao, send WeChat
message to a contact, hail a Didi, etc).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote


@dataclass(slots=True)
class Skill:
    name: str
    app: str
    description: str
    args: list[str] = field(default_factory=list)
    actions: list[dict[str, Any]] = field(default_factory=list)
    sensitive: bool = False  # requires user confirmation (payment / message send / delete)


def _fmt(value: Any, **kw: Any) -> Any:
    if isinstance(value, str):
        return value.format(**kw)
    if isinstance(value, dict):
        return {k: _fmt(v, **kw) for k, v in value.items()}
    if isinstance(value, list):
        return [_fmt(v, **kw) for v in value]
    return value


SKILLS: dict[str, Skill] = {
    "taobao_search": Skill(
        name="taobao_search",
        app="淘宝",
        description="在淘宝搜索商品",
        args=["query"],
        actions=[
            {"type": "open_url", "url": "taobao://s.taobao.com/?q={query_enc}"},
        ],
    ),
    "jd_search": Skill(
        name="jd_search",
        app="京东",
        description="在京东搜索商品",
        args=["query"],
        actions=[
            {"type": "open_url", "url": "openjd://virtual?params=%7B%22sourceValue%22%3A%22{query_enc}%22%2C%22category%22%3A%22jump%22%2C%22des%22%3A%22productList%22%2C%22keyWord%22%3A%22{query_enc}%22%7D"},
        ],
    ),
    "bilibili_search": Skill(
        name="bilibili_search",
        app="B站",
        description="在 B 站搜视频",
        args=["query"],
        actions=[{"type": "open_url", "url": "bilibili://search?keyword={query_enc}"}],
    ),
    "amap_navigate": Skill(
        name="amap_navigate",
        app="高德",
        description="高德地图导航到目的地",
        args=["destination"],
        actions=[{"type": "open_url", "url": "iosamap://poi?sourceApplication=pa&keywords={destination_enc}&dev=0"}],
    ),
    "meituan_search": Skill(
        name="meituan_search",
        app="美团",
        description="美团搜索/找外卖",
        args=["query"],
        actions=[{"type": "open_url", "url": "imeituan://www.meituan.com/search?q={query_enc}"}],
    ),
    "didi_call": Skill(
        name="didi_call",
        app="滴滴",
        description="打开滴滴叫车页(用户需自己确认目的地与下单)",
        args=[],
        actions=[{"type": "activate_app", "bundle_id": "com.xiaojukeji.didi"}],
        sensitive=True,
    ),
    "wechat_open": Skill(
        name="wechat_open",
        app="微信",
        description="打开微信(回到首页)",
        args=[],
        actions=[{"type": "activate_app", "bundle_id": "com.tencent.xin"}],
    ),
    "wechat_send": Skill(
        name="wechat_send",
        app="微信",
        description="给某联系人发送一条消息(敏感:发送动作需用户口头二次确认)",
        args=["contact", "message"],
        actions=[
            {"type": "activate_app", "bundle_id": "com.tencent.xin"},
            {"type": "tap_text", "text": "通讯录"},
            {"type": "tap_text", "text": "{contact}"},
            {"type": "tap_text", "text": "发消息"},
            {"type": "type_text", "text": "{message}"},
            {"type": "tap_text", "text": "发送"},
        ],
        sensitive=True,
    ),
    "alipay_pay": Skill(
        name="alipay_pay",
        app="支付宝",
        description="打开支付宝付款码(敏感:涉及金钱)",
        args=[],
        actions=[{"type": "open_url", "url": "alipays://platformapi/startapp?saId=20000056"}],
        sensitive=True,
    ),
}


def list_skills() -> list[dict[str, Any]]:
    """Tool descriptor list — feed this to the LLM as available tools."""
    return [
        {
            "name": s.name,
            "app": s.app,
            "description": s.description,
            "args": s.args,
            "sensitive": s.sensitive,
        }
        for s in SKILLS.values()
    ]


def expand(skill_name: str, **kwargs: Any) -> tuple[Skill, list[dict[str, Any]]]:
    """Resolve a skill call into a concrete action list. Raises KeyError if unknown."""
    skill = SKILLS[skill_name]
    fmt_kw = dict(kwargs)
    for k in list(fmt_kw):
        if isinstance(fmt_kw[k], str):
            fmt_kw[f"{k}_enc"] = quote(fmt_kw[k])
    actions = [_fmt(a, **fmt_kw) for a in skill.actions]
    return skill, actions
