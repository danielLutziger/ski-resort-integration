import json
from pathlib import Path

from custom_components.ski_resort_recommender.lib.open_meteo import _parse_daily

FIXTURE = Path(__file__).parent / "fixtures" / "open_meteo_response.json"


def test_parse_daily_returns_one_forecast_per_day():
    payload = json.loads(FIXTURE.read_text())
    daily = payload[0]["daily"]

    days = _parse_daily(daily)

    assert len(days) == len(daily["time"])
    assert days[0].day.isoformat() == daily["time"][0]
    assert all(d.sunshine_hours is not None for d in days)
    assert all(d.temp_min_c is not None for d in days)
    assert all(d.temp_max_c is not None for d in days)
    assert all(d.snowfall_cm is not None for d in days)
    assert all(d.wind_max_kmh is not None for d in days)
    assert all(d.weather_code is not None for d in days)
