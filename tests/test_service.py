from datetime import date

from custom_components.ski_resort_recommender.lib.models import DayForecast, Resort
from custom_components.ski_resort_recommender.lib.service import (
    pick_recommendations,
    RecommendationStatus,
)
from custom_components.ski_resort_recommender.lib.settings import Settings

SATURDAY = date(2026, 11, 28)
SUNDAY = date(2026, 11, 29)
WEDNESDAY = date(2026, 11, 25)
TODAY = date(2026, 11, 22)

WEEKEND = frozenset({5, 6})

SETTINGS = Settings(allowed_weekdays=WEEKEND, max_results=3, min_good_score=50.0)


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


def make_day(
    day: date,
    *,
    sun: float = 8,
    snow: float = 10,
    wind: float = 10,
    tmax: float = -2,
    code: int = 0,
    visibility: int = 0,
) -> DayForecast:
    """Create a forecast for day."""
    return DayForecast(
        day=day,
        temp_min_c=tmax - 6,
        temp_max_c=tmax,
        snowfall_cm=snow,
        sunshine_hours=sun,
        wind_max_kmh=wind,
        weather_code=code,
        vision=visibility,
    )


def make_rainy_day(day: date) -> DayForecast:
    return make_day(day, sun=0, snow=0, wind=50, tmax=6, code=63)


def test_only_allowed_weekedays_are_returned() -> None:
    resort = make_resort("flims_laax")
    forecasts = {"flims_laax": [make_day(WEDNESDAY), make_day(SATURDAY)]}

    result = pick_recommendations([resort], forecasts, SETTINGS, today=TODAY)

    days = [r.day.day for r in result.recommendations]

    assert days == [SATURDAY]


def test_same_resort_can_appear_twice() -> None:
    resort = make_resort("laax")
    forecasts = {"laax": [make_day(SATURDAY), make_day(SUNDAY)]}

    result = pick_recommendations([resort], forecasts, SETTINGS, today=TODAY)

    assert [r.resort.key for r in result.recommendations] == ["laax", "laax"]


def test_results_are_sorted_best_first_and_limited() -> None:
    resorts = [make_resort("a"), make_resort("b"), make_resort("c")]
    forecasts = {
        "a": [make_day(SATURDAY, sun=2), make_day(SUNDAY, sun=4)],
        "b": [make_day(SATURDAY, sun=8), make_day(SUNDAY, sun=6)],
        "c": [make_day(SATURDAY, sun=1)],
    }

    result = pick_recommendations(resorts, forecasts, SETTINGS, today=TODAY)

    assert len(result.recommendations) == 3
    totals = [r.score.total for r in result.recommendations]
    assert totals == sorted(totals, reverse=True)
    assert result.recommendations[0].resort.key == "b"


def test_rainy_weekend_still_returns_entries_but_no_good_day() -> None:
    resort = make_resort("laax")
    forecasts = {"laax": [make_rainy_day(SATURDAY), make_rainy_day(SUNDAY)]}

    result = pick_recommendations([resort], forecasts, SETTINGS, today=TODAY)

    assert len(result.recommendations) == 2
    assert result.has_good_day is False


def test_good_day_is_flagged() -> None:
    resort = make_resort("laax")
    forecasts = {"laax": [make_day(SATURDAY)]}

    result = pick_recommendations([resort], forecasts, SETTINGS, today=TODAY)

    assert result.has_good_day is True


def test_no_go_weather_is_never_good_even_with_high_score() -> None:
    resort = make_resort("laax")
    # perfect values for sun/snow/wind/temp, but thunderstorm code
    forecasts = {"laax": [make_day(SATURDAY, code=95)]}

    result = pick_recommendations(
        [resort],
        forecasts,
        Settings(allowed_weekdays=WEEKEND, max_results=3, min_good_score=0.0),
        today=TODAY,
    )

    assert result.recommendations[0].is_good is False


def test_resort_without_forecast_is_skipped() -> None:
    resorts = [make_resort("laax"), make_resort("zermatt")]
    forecasts = {"laax": [make_day(SATURDAY)]}

    result = pick_recommendations(resorts, forecasts, SETTINGS, today=TODAY)

    assert [r.resort.key for r in result.recommendations] == ["laax"]


def test_custom_weekdays_setting() -> None:
    resort = make_resort("laax")
    forecasts = {"laax": [make_day(WEDNESDAY), make_day(SATURDAY)]}
    settings = Settings(
        allowed_weekdays=frozenset({2}), max_results=3, min_good_score=50.0
    )

    result = pick_recommendations([resort], forecasts, settings, today=TODAY)

    assert [r.day.day for r in result.recommendations] == [WEDNESDAY]


def test_today_and_past_days_are_not_recommended() -> None:
    resort = make_resort("laax")
    forecasts = {"laax": [make_day(SATURDAY), make_day(SUNDAY)]}

    # today is the Saturday itself: only the Sunday is in the future
    result = pick_recommendations([resort], forecasts, SETTINGS, today=SATURDAY)

    assert [r.day.day for r in result.recommendations] == [SUNDAY]


def test_past_days_are_not_recommended() -> None:
    resort = make_resort("laax")
    forecasts = {"laax": [make_day(SATURDAY)]}

    result = pick_recommendations(
        [resort], forecasts, SETTINGS, today=date(2026, 12, 1)
    )

    assert result.recommendations == ()


def make_empty_day(day: date) -> DayForecast:
    """Create a day beyond the model horizon: every value is None."""
    return DayForecast(
        day=day,
        temp_min_c=None,
        temp_max_c=None,
        snowfall_cm=None,
        sunshine_hours=None,
        wind_max_kmh=None,
        weather_code=None,
        vision=None,  # your DayForecast has this field
    )


def test_days_without_forecast_data_are_skipped() -> None:
    forecasts = {"laax": [make_empty_day(SATURDAY), make_empty_day(SUNDAY)]}

    result = pick_recommendations(
        [make_resort("laax")], forecasts, SETTINGS, today=TODAY
    )

    assert result.recommendations == ()
    assert result.status is RecommendationStatus.NO_FORECAST


def test_empty_days_do_not_displace_real_days() -> None:
    forecasts = {"laax": [make_empty_day(SATURDAY), make_rainy_day(SUNDAY)]}

    result = pick_recommendations(
        [make_resort("laax")], forecasts, SETTINGS, today=TODAY
    )

    assert [r.day.day for r in result.recommendations] == [SUNDAY]


def test_status_good_day() -> None:
    result = pick_recommendations(
        [make_resort("laax")], {"laax": [make_day(SATURDAY)]}, SETTINGS, today=TODAY
    )

    assert result.status is RecommendationStatus.GOOD_DAY


def test_status_no_good_day_when_scored_but_poor() -> None:
    result = pick_recommendations(
        [make_resort("laax")],
        {"laax": [make_rainy_day(SATURDAY)]},
        SETTINGS,
        today=TODAY,
    )

    assert result.status is RecommendationStatus.NO_GOOD_DAY
