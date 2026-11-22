"""Tests for parsing the Open-Meteo response."""

import json
from datetime import date
from pathlib import Path
from statistics import mean, median

from custom_components.ski_resort_recommender.lib.models import (
    DayForecast,
    Resort,
    WeatherPoint,
)
from custom_components.ski_resort_recommender.lib.open_meteo import (
    _before_opening,
    _combine,
    _coordinates,
    _merge,
    _parse_daily,
    _parse_location,
    _ski_hours,
)

FIXTURES = Path(__file__).parent / "fixtures"
MS_FIXTURE = FIXTURES / "open_meteo_response.json"  # MeteoSwiss daily + hourly
DWD_FIXTURE = FIXTURES / "open_meteo_dwd_response.json"  # DWD daily + hourly


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


def test_parse_location_returns_one_forecast_per_day() -> None:
    """The saved fixture gives one complete DayForecast per day."""
    loc = json.loads(MS_FIXTURE.read_text())[0]

    days = _parse_location(loc, {})

    assert [d.day.isoformat() for d in days] == loc["daily"]["time"]
    for d in days:
        assert d.sunshine_hours is not None
        assert d.daylight_hours is not None
        assert d.temp_max_c is not None
        assert d.weather_code is not None
        assert d.temp_ski_c is not None
        assert d.gust_max_kmh is not None
        assert len(d.weather_codes_ski) == 8  # 09:00-16:00
    # the first two (past) days have no full 48 h window before opening
    assert [d.fresh_snow_cm is None for d in days] == [True, True, False, False, False]
    assert [d.recent_rain_mm is None for d in days] == [True, True, False, False, False]


def test_parse_daily_attaches_visibility_per_day() -> None:
    """Visibility is looked up by date; days without a value get None."""
    daily = json.loads(MS_FIXTURE.read_text())[0]["daily"]
    first = date.fromisoformat(daily["time"][0])

    days = _parse_daily(daily, visibility={first: 1234.0})

    assert days[0].visibility_m == 1234.0
    assert all(d.visibility_m is None for d in days[1:])


HOURLY = {
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


def test_ski_hours_uses_only_ski_hours_and_skips_missing_values() -> None:
    """Night hours and missing values are ignored; one value per day."""
    assert _ski_hours(HOURLY, "visibility", median) == {
        date(2026, 11, 28): 5000,
        date(2026, 11, 30): 800,
    }
    assert _ski_hours(HOURLY, "visibility", max)[date(2026, 11, 28)] == 20000


def test_ski_hours_on_real_response() -> None:
    """Mean temperature and max gust over 09:00-16:00 of the first day."""
    hourly = json.loads(DWD_FIXTURE.read_text())[0]["hourly"]
    first_day = hourly["time"][0][:10]

    def ski_values(key: str) -> list[float]:
        return [
            v
            for t, v in zip(hourly["time"], hourly[key], strict=True)
            if t.startswith(first_day) and 9 <= int(t[11:13]) <= 16
        ]

    day = date.fromisoformat(first_day)
    assert _ski_hours(hourly, "temperature_2m", mean)[day] == mean(
        ski_values("temperature_2m")
    )
    assert _ski_hours(hourly, "wind_gusts_10m", max)[day] == max(
        ski_values("wind_gusts_10m")
    )


def test_fresh_snow_sums_the_48_hours_before_opening() -> None:
    """
    Snow from 09:00 two days before until opening counts; later snow does not.

    Each hourly value is the snow of the hour before its time stamp.
    """
    times = [f"2026-11-{d}T{h:02d}:00" for d in (26, 27, 28) for h in range(24)]
    snow = [0.0] * len(times)
    snow[times.index("2026-11-26T09:00")] = 50  # 08-09 on the 26th: too early
    snow[times.index("2026-11-26T10:00")] = 1  # 09-10: first hour of the window
    snow[times.index("2026-11-28T03:00")] = 10  # overnight storm
    snow[times.index("2026-11-28T09:00")] = 2  # 08-09: just before opening
    snow[times.index("2026-11-28T10:00")] = 7  # 09-10: falls during ski hours

    result = _before_opening({"time": times, "snowfall": snow}, ("snowfall",))

    assert result == {date(2026, 11, 28): 13}  # 26th and 27th lack a full window


def test_combine_matches_both_responses_to_points_by_position() -> None:
    """MeteoSwiss and DWD payloads are merged per point in coordinate order."""
    meteoswiss = json.loads(MS_FIXTURE.read_text())
    dwd = json.loads(DWD_FIXTURE.read_text())
    top = WeatherPoint(name="top", lat=46.8, lon=9.3, elevation_m=2500)
    mid = WeatherPoint(name="mid", lat=46.8, lon=9.3, elevation_m=1800)

    forecasts = _combine([make_resort("a", top, mid)], meteoswiss, dwd)

    assert list(forecasts) == ["a"]
    assert list(forecasts["a"]) == ["top", "mid"]
    assert [d.day.isoformat() for d in forecasts["a"]["mid"]] == dwd[1]["daily"]["time"]
    # DWD visibility is attached to the MeteoSwiss days too
    assert any(d.visibility_m is not None for d in forecasts["a"]["mid"])


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
        "daylight_duration": [32000],
        "weather_code": [None],
    }

    (day,) = _parse_daily(daily)

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
        daylight_hours=9,
        weather_code=None,
        visibility_m=None,
        temp_ski_c=None,
        gust_max_kmh=None,
        fresh_snow_cm=None,
    )


def test_merge_prefers_meteoswiss_and_fills_gaps_from_dwd() -> None:
    """MeteoSwiss days with data win; empty or missing days come from DWD."""
    thu, fri, sat = date(2026, 11, 26), date(2026, 11, 27), date(2026, 11, 28)
    meteoswiss = [make_forecast(thu, 5), make_forecast(fri, None)]
    dwd = [make_forecast(thu, 1), make_forecast(fri, 2), make_forecast(sat, 3)]

    merged = _merge(meteoswiss, dwd)

    assert [(d.day, d.sunshine_hours) for d in merged] == [(thu, 5), (fri, 2), (sat, 3)]


def test_rain_before_opening_adds_rain_and_showers() -> None:
    """Liquid precipitation = large-scale rain + convective showers (mm)."""
    times = [f"2026-11-{d}T{h:02d}:00" for d in (26, 27, 28) for h in range(24)]
    rain = [0.0] * len(times)
    showers = [0.0] * len(times)
    rain[times.index("2026-11-27T12:00")] = 1.5
    showers[times.index("2026-11-27T13:00")] = 2.0
    showers[times.index("2026-11-28T12:00")] = 9.0  # during ski hours: not before

    result = _before_opening(
        {"time": times, "rain": rain, "showers": showers}, ("rain", "showers")
    )

    assert result == {date(2026, 11, 28): 3.5}
