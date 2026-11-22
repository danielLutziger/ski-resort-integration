"""Tests for parsing the Open-Meteo response."""

import json
from datetime import date
from pathlib import Path
from statistics import median

from custom_components.ski_resort_recommender.lib.models import (
    DayForecast,
    Resort,
    WeatherPoint,
)
from custom_components.ski_resort_recommender.lib.open_meteo import (
    _combine,
    _coordinates,
    _merge,
    _parse_daily,
    _ski_hours_visibility,
)

FIXTURES = Path(__file__).parent / "fixtures"
DAILY_FIXTURE = FIXTURES / "open_meteo_response.json"
DWD_FIXTURE = FIXTURES / "open_meteo_dwd_response.json"  # daily + hourly visibility


def make_resort(key: str, *points: WeatherPoint) -> Resort:
    """Create a resort with the given points."""
    return Resort(
        key=key,
        name=key,
        points=points,
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
    hourly = json.loads(DWD_FIXTURE.read_text())[0]["hourly"]

    result = _ski_hours_visibility(hourly)

    first_day = hourly["time"][0][:10]
    ski_values = [
        v
        for t, v in zip(hourly["time"], hourly["visibility"], strict=True)
        if t.startswith(first_day) and 9 <= int(t[11:13]) <= 16
    ]
    assert len(result) == 2
    assert result[date.fromisoformat(first_day)] == median(ski_values)


def test_combine_matches_both_responses_to_points_by_position() -> None:
    """MeteoSwiss and DWD payloads are merged per point in coordinate order."""
    daily = json.loads(DAILY_FIXTURE.read_text())
    dwd = json.loads(DWD_FIXTURE.read_text())
    top = WeatherPoint(name="top", lat=46.8, lon=9.3, elevation_m=2500)
    mid = WeatherPoint(name="mid", lat=46.8, lon=9.3, elevation_m=1800)

    forecasts = _combine([make_resort("a", top, mid)], daily, dwd)

    assert list(forecasts) == ["a"]
    assert list(forecasts["a"]) == ["top", "mid"]
    # the fixtures cover different dates: the result has the days of both
    days = {*daily[1]["daily"]["time"], *dwd[1]["daily"]["time"]}
    assert [d.day.isoformat() for d in forecasts["a"]["mid"]] == sorted(days)


def test_coordinates_list_all_points_in_order_with_elevation() -> None:
    """One request location per point; Open-Meteo gets the station elevation."""
    resorts = [
        make_resort(
            "a",
            WeatherPoint(name="top", lat=46.1, lon=9.1, elevation_m=2500),
            WeatherPoint(name="mid", lat=46.2, lon=9.2, elevation_m=1800),
        ),
        make_resort("b", WeatherPoint(name="x", lat=47.0, lon=10.0, elevation_m=2000)),
    ]

    params = _coordinates(resorts)

    assert params == {
        "latitude": "46.1,46.2,47.0",
        "longitude": "9.1,9.2,10.0",
        "elevation": "2500,1800,2000",
    }


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


def make_forecast(day: date, sun: float | None) -> DayForecast:
    """Create a day that only has sunshine (None = no data)."""
    return DayForecast(
        day=day,
        temp_min_c=None,
        temp_max_c=None,
        snowfall_cm=None,
        sunshine_hours=sun,
        wind_max_kmh=None,
        weather_code=None,
        visibility_m=None,
    )


def test_merge_prefers_meteoswiss_and_fills_gaps_from_dwd() -> None:
    """MeteoSwiss days with data win; empty or missing days come from DWD."""
    thu, fri, sat = date(2026, 11, 26), date(2026, 11, 27), date(2026, 11, 28)
    meteoswiss = [make_forecast(thu, 5), make_forecast(fri, None)]
    dwd = [make_forecast(thu, 1), make_forecast(fri, 2), make_forecast(sat, 3)]

    merged = _merge(meteoswiss, dwd)

    assert [(d.day, d.sunshine_hours) for d in merged] == [(thu, 5), (fri, 2), (sat, 3)]
