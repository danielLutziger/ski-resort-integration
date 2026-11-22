"""Tests for parsing the Open-Meteo response."""

import json
from datetime import date
from pathlib import Path
from statistics import median

from custom_components.ski_resort_recommender.lib.models import Resort
from custom_components.ski_resort_recommender.lib.open_meteo import (
    _combine,
    _parse_daily,
    _ski_hours_visibility,
)

FIXTURES = Path(__file__).parent / "fixtures"
DAILY_FIXTURE = FIXTURES / "open_meteo_response.json"
HOURLY_FIXTURE = FIXTURES / "open_meteo_visibility_response.json"


def make_resort(key: str) -> Resort:
    """Create a resort."""
    return Resort(
        key=key,
        name=key,
        lat=46.8,
        lon=9.3,
        meteoswiss_point_id=None,
        station="Chur",
        day_price_chf=None,
    )


def test_parse_daily_returns_one_forecast_per_day() -> None:
    """The saved fixture gives one DayForecast per day."""
    payload = json.loads(DAILY_FIXTURE.read_text())
    daily = payload[0]["daily"]

    days = _parse_daily(daily, {})

    assert len(days) == len(daily["time"])
    assert days[0].day.isoformat() == daily["time"][0]
    assert all(d.sunshine_hours is not None for d in days)
    assert all(d.temp_min_c is not None for d in days)
    assert all(d.temp_max_c is not None for d in days)
    assert all(d.snowfall_cm is not None for d in days)
    assert all(d.wind_max_kmh is not None for d in days)
    assert all(d.weather_code is not None for d in days)


def test_parse_daily_attaches_visibility_per_day() -> None:
    """Visibility is looked up by date; days without a value get None."""
    daily = json.loads(DAILY_FIXTURE.read_text())[0]["daily"]
    first = date.fromisoformat(daily["time"][0])

    days = _parse_daily(daily, {first: 1234.0})

    assert days[0].visibility_m == 1234.0
    assert all(d.visibility_m is None for d in days[1:])


def test_ski_hours_visibility_uses_median_of_ski_hours_only() -> None:
    """Night hours and missing values are ignored; one value per day."""
    hourly = {
        "time": [
            "2026-11-28T08:00",  # before ski hours
            "2026-11-28T09:00",
            "2026-11-28T12:00",
            "2026-11-28T16:00",
            "2026-11-28T17:00",  # after ski hours
            "2026-11-29T10:00",
            "2026-11-30T10:00",
        ],
        "visibility": [10, 300, 5000, 20000, 10, None, 800],
    }

    result = _ski_hours_visibility(hourly)

    assert result == {date(2026, 11, 28): 5000, date(2026, 11, 30): 800}


def test_ski_hours_visibility_on_real_response() -> None:
    """The saved hourly fixture gives one median per day."""
    hourly = json.loads(HOURLY_FIXTURE.read_text())[0]["hourly"]

    result = _ski_hours_visibility(hourly)

    first_day = hourly["time"][0][:10]
    ski_values = [
        v
        for t, v in zip(hourly["time"], hourly["visibility"], strict=True)
        if t.startswith(first_day) and 9 <= int(t[11:13]) <= 16
    ]
    assert len(result) == 2
    assert result[date.fromisoformat(first_day)] == median(ski_values)


def test_combine_matches_both_responses_to_resorts_by_position() -> None:
    """Daily and hourly payloads are merged per resort in coordinate order."""
    daily = json.loads(DAILY_FIXTURE.read_text())
    hourly = json.loads(HOURLY_FIXTURE.read_text())
    resorts = [make_resort("a"), make_resort("b")]

    forecasts = _combine(resorts, daily, hourly)

    assert list(forecasts) == ["a", "b"]
    assert len(forecasts["a"]) == len(daily[0]["daily"]["time"])


def test_days_beyond_the_model_horizon_have_no_data() -> None:
    """All-None days from the API stay None, so the service can skip them."""
    daily = {
        "time": ["2026-11-27"],
        "temperature_2m_min": [None],
        "temperature_2m_max": [None],
        "snowfall_sum": [None],
        "sunshine_duration": [None],
        "wind_speed_10m_max": [None],
        "weather_code": [None],
    }

    (day,) = _parse_daily(daily, {})

    assert day.sunshine_hours is None
    assert day.has_data is False
