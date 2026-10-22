"""Weather snapshot for the page header, from Open-Meteo (free, no key, MeteoSwiss-backed models).

Fetched once per nightly build; stored in the page snapshot so archive pages keep their forecast.
A failure returns None and the page simply renders without the weather block."""
from __future__ import annotations

import json
import logging
from datetime import date
from urllib.parse import urlencode

from common import http_get

log = logging.getLogger("weather")
API = "https://api.open-meteo.com/v1/forecast"
SLOTS = [("Morning", 8), ("Afternoon", 14), ("Evening", 19)]

# WMO weather interpretation codes -> (label, icon)
WMO = {
    0: ("Clear", "☀️"), 1: ("Mostly clear", "🌤️"), 2: ("Partly cloudy", "⛅"), 3: ("Overcast", "☁️"),
    45: ("Fog", "🌫️"), 48: ("Freezing fog", "🌫️"),
    51: ("Light drizzle", "🌦️"), 53: ("Drizzle", "🌦️"), 55: ("Heavy drizzle", "🌧️"),
    56: ("Freezing drizzle", "🌧️"), 57: ("Freezing drizzle", "🌧️"),
    61: ("Light rain", "🌦️"), 63: ("Rain", "🌧️"), 65: ("Heavy rain", "🌧️"),
    66: ("Freezing rain", "🌧️"), 67: ("Freezing rain", "🌧️"),
    71: ("Light snow", "🌨️"), 73: ("Snow", "🌨️"), 75: ("Heavy snow", "❄️"), 77: ("Snow grains", "🌨️"),
    80: ("Light showers", "🌦️"), 81: ("Showers", "🌧️"), 82: ("Heavy showers", "🌧️"),
    85: ("Snow showers", "🌨️"), 86: ("Heavy snow showers", "❄️"),
    95: ("Thunderstorm", "⛈️"), 96: ("Thunderstorm, hail", "⛈️"), 99: ("Thunderstorm, hail", "⛈️"),
}
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _wmo(code) -> tuple[str, str]:
    try:
        return WMO.get(int(code), ("—", "🌡️"))
    except (TypeError, ValueError):
        return ("—", "🌡️")


def _r(x):
    return None if x is None else round(x)


def fetch_weather(cfg: dict, getter=http_get) -> dict | None:
    w = cfg.get("weather")
    if not w:
        return None
    q = {
        "latitude": w["lat"], "longitude": w["lon"], "timezone": cfg["settings"]["timezone"],
        "forecast_days": int(w.get("days", 10)), "wind_speed_unit": "kmh",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,"
                 "precipitation_probability_max,wind_speed_10m_max,sunrise,sunset,uv_index_max",
        "hourly": "temperature_2m,weather_code,precipitation_probability",
    }
    try:
        _, body, _, _ = getter(f"{API}?{urlencode(q)}", 15.0, cfg["settings"].get("user_agent"))
        return parse_weather(json.loads(body), w.get("name", ""))
    except Exception as e:  # noqa: BLE001
        log.warning("weather failed: %s: %s", type(e).__name__, e)
        return None


def parse_weather(data: dict, name: str) -> dict | None:
    d, h = data.get("daily") or {}, data.get("hourly") or {}
    if not d.get("time"):
        return None
    days = []
    for i, t in enumerate(d["time"]):
        dt = date.fromisoformat(t)
        label, icon = _wmo(d["weather_code"][i])
        days.append({
            "date": t, "dow": "Today" if i == 0 else DAYS[dt.weekday()], "dm": f"{dt.day:02d}.{dt.month:02d}.",
            "label": label, "icon": icon,
            "hi": _r(d["temperature_2m_max"][i]), "lo": _r(d["temperature_2m_min"][i]),
            "rain_mm": round(d["precipitation_sum"][i] or 0, 1),
            "rain_pct": _r((d.get("precipitation_probability_max") or [None] * (i + 1))[i]),
            "wind": _r(d["wind_speed_10m_max"][i]),
            "uv": _r((d.get("uv_index_max") or [None] * (i + 1))[i]),
            "sunrise": (d.get("sunrise") or [""] * (i + 1))[i][-5:],
            "sunset": (d.get("sunset") or [""] * (i + 1))[i][-5:],
        })
    lo = min(x["lo"] for x in days if x["lo"] is not None)
    hi = max(x["hi"] for x in days if x["hi"] is not None)
    span = max(hi - lo, 1)
    for x in days:  # position of each day's range on a shared scale, for the range bars
        x["bar_l"] = round(100 * (x["lo"] - lo) / span)
        x["bar_w"] = max(round(100 * (x["hi"] - x["lo"]) / span), 4)
    slots = []
    today = d["time"][0]
    for name_, hour in SLOTS:
        key = f"{today}T{hour:02d}:00"
        if key in (h.get("time") or []):
            j = h["time"].index(key)
            label, icon = _wmo(h["weather_code"][j])
            slots.append({"name": name_, "temp": _r(h["temperature_2m"][j]), "icon": icon, "label": label,
                          "rain_pct": _r((h.get("precipitation_probability") or [None] * (j + 1))[j])})
    return {"place": name, "today": days[0], "slots": slots, "days": days, "lo": lo, "hi": hi}
