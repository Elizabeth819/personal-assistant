from pa.agent.intent import plan_actions


def test_say_fallback():
    acts = plan_actions("今天天气不错", "嗯,挺好的")
    assert acts[-1] == {"type": "say", "text": "嗯,挺好的"}
    assert len(acts) == 1


def test_play_music():
    acts = plan_actions("放周杰伦的晴天", "好的")
    assert acts[0]["type"] == "play_music"
    assert "周杰伦" in acts[0]["query"]


def test_open_app():
    acts = plan_actions("打开微信", "好")
    assert acts[0] == {"type": "open_app", "app": "微信"}


def test_timer():
    acts = plan_actions("10分钟后提醒我喝水", "好的")
    assert acts[0]["type"] == "set_timer"
    assert acts[0]["seconds"] == 600


def test_navigate():
    acts = plan_actions("导航到天安门", "走")
    assert acts[0] == {"type": "navigate", "destination": "天安门"}


def test_url():
    acts = plan_actions("打开 https://example.com", "ok")
    assert any(a["type"] == "open_url" for a in acts)


def test_dial():
    acts = plan_actions("打电话给 13800138000", "好")
    assert any(a["type"] == "open_url" and a["url"] == "tel://13800138000" for a in acts)


def test_search_taobao():
    acts = plan_actions("淘宝搜AirPods", "好")
    assert any(a["type"] == "open_url" and a["url"].startswith("taobao://") for a in acts)


def test_weather_query():
    acts = plan_actions("上海明天会下雨吗", "好")
    assert any(a["type"] == "weather" and a["when"] == "tomorrow" for a in acts)


def test_weather_not_query():
    acts = plan_actions("今天天气不错", "嗯")
    assert all(a["type"] != "weather" for a in acts)


def test_chain_open_then_search():
    acts = plan_actions("打开淘宝然后搜AirPods", "好")
    types = [a["type"] for a in acts]
    assert "open_app" in types and "open_url" in types


def test_screen_explain():
    acts = plan_actions("帮我看看屏幕上是什么", "好")
    assert any(a["type"] == "screen_explain" for a in acts)


def test_react_routing_explicit():
    acts = plan_actions("用 react agent 帮我把京东购物车清空", "好")
    assert any(a["type"] == "react" for a in acts)


def test_react_routing_implicit_help():
    acts = plan_actions("帮我退掉昨天那笔京东订单", "好")
    assert any(a["type"] == "react" for a in acts)


def test_react_not_triggered_for_simple_open():
    acts = plan_actions("打开微信", "好")
    types = [a["type"] for a in acts]
    assert "react" not in types
    assert "open_app" in types
