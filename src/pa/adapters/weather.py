"""Open-Meteo weather lookup. No API key required.

Uses geocoding-api.open-meteo.com to resolve city → lat/lon, then
api.open-meteo.com for forecast.
"""

from __future__ import annotations

from typing import Any

import httpx

from pa.core import get_logger

log = get_logger(__name__)

_WEATHER_CODES = {
    0: "晴", 1: "晴间多云", 2: "多云", 3: "阴",
    45: "雾", 48: "雾凇",
    51: "毛毛雨", 53: "中等毛毛雨", 55: "密集毛毛雨",
    56: "冻毛毛雨", 57: "强冻毛毛雨",
    61: "小雨", 63: "中雨", 65: "大雨",
    66: "冻雨", 67: "强冻雨",
    71: "小雪", 73: "中雪", 75: "大雪", 77: "雪粒",
    80: "阵雨", 81: "中阵雨", 82: "强阵雨",
    85: "小阵雪", 86: "大阵雪",
    95: "雷暴", 96: "雷暴伴小冰雹", 99: "雷暴伴大冰雹",
}


async def _geocode(city: str) -> tuple[float, float, str] | None:
    if city in {"current", "", "本地", "这里"}:
        return None
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 1, "language": "zh"},
        )
        r.raise_for_status()
        results = r.json().get("results") or []
        if not results:
            return None
        g = results[0]
        return float(g["latitude"]), float(g["longitude"]), g.get("name", city)


async def execute(action: dict[str, Any]) -> dict[str, Any]:
    city = action.get("city", "current")
    when = action.get("when", "today")
    geo = await _geocode(city)
    if not geo:
        return {"action": "weather", "ok": False, "error": f"未找到城市: {city}"}
    lat, lon, name = geo
    days = 7 if when == "week" else 3
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat, "longitude": lon,
                "current": "temperature_2m,weather_code,wind_speed_10m",
                "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                "forecast_days": days,
                "timezone": "auto",
            },
        )
        r.raise_for_status()
        d = r.json()
    cur = d.get("current", {})
    daily = d.get("daily", {})

    def desc(code: int) -> str:
        return _WEATHER_CODES.get(code, f"天气代码{code}")

    summary = ""
    if when == "today":
        t = cur.get("temperature_2m")
        wc = desc(int(cur.get("weather_code", 0)))
        wind = cur.get("wind_speed_10m")
        rain = (daily.get("precipitation_probability_max") or [0])[0]
        summary = f"{name} 现在 {wc}, {t}°C, 风速 {wind} km/h, 今日降水概率 {rain}%。"
    elif when == "tomorrow":
        i = 1
        wc = desc(int(daily.get("weather_code", [0, 0])[i]))
        hi = daily.get("temperature_2m_max", [None, None])[i]
        lo = daily.get("temperature_2m_min", [None, None])[i]
        rain = daily.get("precipitation_probability_max", [0, 0])[i]
        summary = f"{name} 明天 {wc}, {lo}~{hi}°C, 降水概率 {rain}%。"
    elif when == "+2d":
        i = 2
        wc = desc(int(daily.get("weather_code", [0, 0, 0])[i]))
        hi = daily.get("temperature_2m_max", [None, None, None])[i]
        lo = daily.get("temperature_2m_min", [None, None, None])[i]
        summary = f"{name} 后天 {wc}, {lo}~{hi}°C。"
    else:  # week
        codes = daily.get("weather_code", [])
        his = daily.get("temperature_2m_max", [])
        los = daily.get("temperature_2m_min", [])
        rows = []
        days_zh = ["今天", "明天", "后天", "+3", "+4", "+5", "+6"]
        for i, c in enumerate(codes[:7]):
            rows.append(f"{days_zh[i]} {desc(int(c))} {los[i]}~{his[i]}°")
        summary = f"{name} 一周: " + "; ".join(rows)
    return {"action": "weather", "ok": True, "city": name, "summary": summary}
