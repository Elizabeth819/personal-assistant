"""ReAct loop on iPhone: vision → thought → action → repeat.

Given a high-level goal ("帮我退掉昨天那笔京东订单"), the agent:
  1. screenshot the current screen
  2. ask GPT-4 vision: "what do you see? what's the next single action toward <goal>?"
     → expects JSON: {"thought": "...", "action": {...}, "done": bool, "answer": "..."}
  3. execute that action via ios_wda
  4. loop until done=true or max_steps reached

Each step is recorded so the caller can inspect the trace.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any

import httpx

from pa.adapters import ios_wda
from pa.core import get_logger, get_settings

log = get_logger(__name__)


@dataclass(slots=True)
class ReactStep:
    step: int
    thought: str
    action: dict[str, Any] | None
    result: dict[str, Any] | None
    done: bool
    answer: str | None


@dataclass(slots=True)
class ReactRun:
    goal: str
    steps: list[ReactStep] = field(default_factory=list)
    final_answer: str | None = None
    success: bool = False


_SYSTEM = (
    "你是一个 iPhone 自动化代理。我会给你当前屏幕截图和一个高层目标。"
    "你必须**只输出一个 JSON 对象**(不要 markdown,不要解释外的文字),格式:\n"
    '{"thought":"<你的思考>", "action":{"type":"...","..."}, "done": false, "answer": null}\n'
    "支持的 action.type:\n"
    '  - {"type":"tap_text","text":"<可见文字>"}    点击屏幕上某段可见文字\n'
    '  - {"type":"tap_xy","x":<int>,"y":<int>}      点击绝对坐标\n'
    '  - {"type":"type_text","text":"<内容>"}        在当前输入框输入\n'
    '  - {"type":"swipe","direction":"up|down|left|right"} 滑动一屏\n'
    '  - {"type":"open_url","url":"<scheme://...>"} 打开 deeplink 或网址\n'
    '  - {"type":"activate_app","bundle_id":"..."} 切换到指定 app\n'
    '  - {"type":"press_home"}                       回到主屏(用于脱困)\n'
    "通用准则:\n"
    "  1. 每一步只做一个动作,不要批量。回答简短。\n"
    "  2. 优先 tap_text(更稳),不确定坐标时不要乱猜 tap_xy。\n"
    "  3. 如果连续 2 步在同一界面没进展(看历史),换策略:swipe down 退出键盘 / 点'取消'/'完成'/'<' 返回 / press_home 重来。\n"
    "  4. 看到搜索框已激活但无结果,优先点'取消'按钮或屏幕空白处,而不是按 X 图标。\n"
    "  5. 如果目标只是查看某个信息(版本号、时间、天气等),看到就立即 done=true,把信息写进 answer,不要继续点。\n"
    "  6. 如果 4 步内仍找不到入口,考虑 press_home 然后用 open_url 走 deeplink(如 prefs:root=General)。\n"
    "  7. 目标达成时 done=true,把要返回给用户的中文短句写在 answer。"
)


def _extract_json(text: str) -> dict[str, Any] | None:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)  # type: ignore[no-any-return]
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))  # type: ignore[no-any-return]
            except Exception:
                return None
    return None


async def _ask_vlm(goal: str, screenshot_b64: str, history: str) -> dict[str, Any] | None:
    s = get_settings()
    url = (
        f"{s.azure_openai_endpoint.rstrip('/')}/openai/deployments/"
        f"{s.azure_chat_deployment}/chat/completions?api-version={s.azure_openai_api_version}"
    )
    user_content: list[dict[str, Any]] = [
        {"type": "text", "text": f"目标: {goal}\n\n之前的步骤:\n{history or '(无)'}\n\n当前屏幕:"},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{screenshot_b64}"}},
    ]
    body = {
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user_content},
        ],
        "max_tokens": 400,
        "temperature": 0.2,
    }
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(
            url,
            headers={"api-key": s.azure_openai_api_key, "Content-Type": "application/json"},
            json=body,
        )
        r.raise_for_status()
        text = r.json()["choices"][0]["message"]["content"]
    return _extract_json(text)


async def run(goal: str, *, max_steps: int = 10) -> ReactRun:
    run = ReactRun(goal=goal)
    history_lines: list[str] = []
    recent_actions: list[str] = []

    for step in range(1, max_steps + 1):
        shot = await ios_wda.screenshot_b64()
        if not shot:
            run.steps.append(
                ReactStep(step, "screenshot failed", None, None, True, "无法截屏,请检查 WDA")
            )
            return run

        try:
            decision = await _ask_vlm(goal, shot, "\n".join(history_lines[-6:]))
        except Exception as exc:
            log.exception("react.vlm_failed")
            run.steps.append(
                ReactStep(step, f"vlm error: {exc}", None, None, True, "视觉模型调用失败")
            )
            return run

        if not decision:
            run.steps.append(
                ReactStep(step, "model returned non-JSON", None, None, True, "模型输出格式异常")
            )
            return run

        thought = str(decision.get("thought", ""))[:300]
        done = bool(decision.get("done"))
        answer = decision.get("answer")
        action = decision.get("action")

        if done:
            run.steps.append(ReactStep(step, thought, action, None, True, answer))
            run.final_answer = str(answer) if answer else None
            run.success = True
            return run

        if not action or not isinstance(action, dict) or "type" not in action:
            run.steps.append(
                ReactStep(step, thought, action, None, True, "模型没给出有效 action")
            )
            return run

        sig = f"{action.get('type')}:{action.get('text') or action.get('url') or action.get('direction') or ''}"
        recent_actions.append(sig)
        if len(recent_actions) >= 3 and recent_actions[-1] == recent_actions[-2] == recent_actions[-3]:
            log.warning("react.stuck_detected", sig=sig)
            rescue = {"type": "press_home"}
            try:
                rescue_result = await ios_wda.execute(rescue)
            except Exception as exc:
                rescue_result = {"ok": False, "error": str(exc)}
            run.steps.append(
                ReactStep(step, f"stuck on {sig} — auto press_home", rescue, rescue_result, False, None)
            )
            history_lines.append(f"step{step}: 卡住 → press_home(自动脱困) → ok")
            recent_actions.clear()
            continue

        try:
            result = await ios_wda.execute(action)
        except Exception as exc:
            log.exception("react.execute_failed")
            result = {"ok": False, "error": str(exc)}

        run.steps.append(ReactStep(step, thought, action, result, False, None))
        history_lines.append(
            f"step{step}: {thought[:80]} → {action.get('type')} → "
            f"{'ok' if result.get('ok') else 'fail'}"
        )

    run.steps.append(
        ReactStep(max_steps + 1, "max steps reached", None, None, True, "步数用完仍未完成")
    )
    return run


def to_dict(run: ReactRun) -> dict[str, Any]:
    return {
        "goal": run.goal,
        "success": run.success,
        "final_answer": run.final_answer,
        "steps": [asdict(s) for s in run.steps],
    }
