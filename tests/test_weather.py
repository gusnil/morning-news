import json
from datetime import date, timedelta
from weather import fetch_weather, parse_weather

DATA = {
    "daily": {
        "time": [(date(2026, 10, 23) + timedelta(days=d)).isoformat() for d in range(10)],
        "weather_code": [61, 0, 3, 95, 71, 2, 45, 80, 1, 63],
        "temperature_2m_max": [14.4, 16.2, 12.0, 18.9, 2.1, 10.0, 9.4, 11.0, 13.0, 12.0],
        "temperature_2m_min": [7.6, 6.0, 5.1, 9.0, -1.2, 3.0, 4.0, 5.0, 6.0, 7.0],
        "precipitation_sum": [4.2, 0, 0.1, 12, 3, 0, 0, 2, 0, 5],
        "precipitation_probability_max": [80, 5, 10, 70, 60, 0, 10, 40, 0, 90],
        "wind_speed_10m_max": [22.1, 10, 8, 30, 15, 9, 7, 12, 10, 20],
        "uv_index_max": [2.1, 3, 2, 3, 1, 2, 1, 2, 2, 1],
        "sunrise": ["2026-10-23T07:59"] * 10, "sunset": ["2026-10-23T18:22"] * 10,
    },
    "hourly": {"time": ["2026-10-23T08:00", "2026-10-23T14:00", "2026-10-23T19:00"],
               "temperature_2m": [8.2, 13.9, 10.4], "weather_code": [61, 3, 0],
               "precipitation_probability": [75, 30, 0]},
}


def test_parse_weather():
    w = parse_weather(DATA, "Münchenstein")
    assert w["today"]["dow"] == "Today" and w["today"]["icon"] == "🌦️" and w["today"]["hi"] == 14
    assert len(w["days"]) == 10 and [s["name"] for s in w["slots"]] == ["Morning", "Afternoon", "Evening"]
    assert w["lo"] == -1 and w["hi"] == 19
    cold = w["days"][4]
    assert cold["bar_l"] == 0 and all(0 <= d["bar_l"] <= 100 and d["bar_l"] + d["bar_w"] <= 104 for d in w["days"])


def test_fetch_weather_failure_returns_none():
    cfg = {"weather": {"lat": 1, "lon": 2}, "settings": {"timezone": "Europe/Zurich"}}
    def bad(*a, **k):
        raise OSError("down")
    assert fetch_weather(cfg, bad) is None
    assert fetch_weather(cfg, lambda *a: (200, json.dumps(DATA).encode(), "", "")) ["place"] == ""
