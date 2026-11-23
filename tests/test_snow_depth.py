"""Tests for apply_measured_depth(): measured base + model change."""

from dataclasses import replace
from datetime import date, timedelta

import pytest

from custom_components.ski_resort_recommender.lib.models import (
    DayForecast,
    Resort,
    SnowStation,
    WeatherPoint,
)
from custom_components.ski_resort_recommender.lib.snow_depth import (
    apply_measured_depth,
)

TODAY = date(2026, 11, 23)
LA_FUORCLA = SnowStation(code="CMA2", name="La Fuorcla", elevation_m=2325)
ELM = SnowStation(code="ELM2", name="Chüebodensee", elevation_m=2058)


def make_resort(*stations: SnowStation) -> Resort:
    """Create a resort with one point and the given stations."""
    return Resort(
        key="laax",
        name="Laax",
        points=(WeatherPoint(name="top", lat=46.8, lon=9.2, elevation_m=2200),),
        meteoswiss_point_id=None,
        station="",
        day_price_chf=None,
        snow_stations=stations,
    )


def make_days(*depths: float | None) -> list[DayForecast]:
    """Days from today on with the given model snow depths."""
    empty = DayForecast(
        day=TODAY,
        temp_min_c=None,
        temp_max_c=None,
        snowfall_cm=None,
        sunshine_hours=None,
        daylight_hours=None,
        weather_code=None,
        visibility_m=None,
        temp_ski_c=None,
        gust_max_kmh=None,
        fresh_snow_cm=None,
    )
    return [
        replace(empty, day=TODAY + timedelta(days=i), snow_depth_cm=d)
        for i, d in enumerate(depths)
    ]


def depths(resort: Resort, model: list[DayForecast], measured: dict) -> list:
    """Snow depths of the point after the correction."""
    forecasts = apply_measured_depth(
        [resort], {"laax": {"top": model}}, measured, TODAY
    )
    return [d.snow_depth_cm for d in forecasts["laax"]["top"]]


def test_measured_base_plus_the_model_change() -> None:
    """Model 40 today, +10 new snow, -15 melting: measured 74 moves the same way."""
    model = make_days(40, 50, 35)

    assert depths(make_resort(LA_FUORCLA), model, {"CMA2": 74}) == [74, 84, 69]


def test_mean_of_the_stations_and_never_below_zero() -> None:
    """Several stations: their mean is the base; melting stops at 0."""
    model = make_days(40, 0)

    result = depths(make_resort(LA_FUORCLA, ELM), model, {"CMA2": 30, "ELM2": 20})

    assert result == [25, 0]


def test_without_model_values_the_base_is_used() -> None:
    """No model depth today or that day: the measured base alone."""
    assert depths(make_resort(LA_FUORCLA), make_days(None, 50), {"CMA2": 74}) == [
        74,
        74,
    ]
    assert depths(make_resort(LA_FUORCLA), make_days(40, None), {"CMA2": 74}) == [
        74,
        74,
    ]


@pytest.mark.parametrize(
    ("stations", "measured"),
    [((), {"CMA2": 74}), ((LA_FUORCLA,), {}), ((LA_FUORCLA,), {"OTHER": 74})],
)
def test_without_a_measurement_the_model_stays(
    stations: tuple[SnowStation, ...], measured: dict
) -> None:
    """No station or no value of its stations: model depth unchanged."""
    model = make_days(40, 50)

    assert depths(make_resort(*stations), model, measured) == [40, 50]
