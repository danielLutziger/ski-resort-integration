"""Tests for score_day()."""

from dataclasses import replace
from datetime import date

from custom_components.ski_resort_recommender.lib.models import DayForecast
from custom_components.ski_resort_recommender.lib.scoring import (
    combine_scores,
    score_day,
)

CLEAR_DAY = DayForecast(
    day=date(2026, 12, 5),
    temp_min_c=-8,
    temp_max_c=2,
    snowfall_cm=0,
    sunshine_hours=8,
    wind_max_kmh=10,
    weather_code=0,
    visibility_m=20_000,
)


def test_sunny_cold_day_beats_rainy_day() -> None:
    """A clear day scores higher than a rainy one."""
    rainy = replace(CLEAR_DAY, weather_code=63)

    assert score_day(CLEAR_DAY).total > score_day(rainy).total


def test_fog_scores_lower_than_clear_view() -> None:
    """Low visibility during ski hours costs points."""
    foggy = replace(CLEAR_DAY, visibility_m=300)

    assert score_day(foggy).total < score_day(CLEAR_DAY).total


def test_visibility_penalty_scales_between_thresholds() -> None:
    """No penalty at 5 km or more, full penalty at 1 km or less, linear between."""
    points = {
        v: score_day(replace(CLEAR_DAY, visibility_m=v)).reasons["visibility"]
        for v in (20_000, 5_000, 3_000, 1_000, 200)
    }

    assert points[20_000] == 0
    assert points[5_000] == 0
    assert points[3_000] == -15
    assert points[1_000] == -30
    assert points[200] == -30


def test_unknown_visibility_is_neutral() -> None:
    """Beyond the visibility horizon there is no penalty."""
    unknown = replace(CLEAR_DAY, visibility_m=None)

    assert score_day(unknown).reasons["visibility"] == 0


def test_bad_weather_good_view_beats_good_weather_bad_view() -> None:
    """Snowfall with a clear view beats a dry day in the fog."""
    snowing_clear_view = replace(CLEAR_DAY, weather_code=73, visibility_m=20_000)
    dry_in_fog = replace(CLEAR_DAY, weather_code=3, visibility_m=300)

    assert score_day(snowing_clear_view).total > score_day(dry_in_fog).total


def test_good_view_snow_beats_medium_view_snow() -> None:
    """On a snow day, better visibility ranks higher."""
    snow = replace(CLEAR_DAY, snowfall_cm=15, weather_code=73)

    good_view = replace(snow, visibility_m=10_000)
    medium_view = replace(snow, visibility_m=2_500)

    assert score_day(good_view).total > score_day(medium_view).total


def test_combine_scores_is_a_weighted_average() -> None:
    """Total and every reason are averaged with the point weights."""
    good, bad = score_day(CLEAR_DAY), score_day(replace(CLEAR_DAY, sunshine_hours=0))

    combined = combine_scores([(3, good), (1, bad)])

    assert combined.total == (3 * good.total + bad.total) / 4
    assert combined.reasons["sun"] == (3 * good.reasons["sun"] + bad.reasons["sun"]) / 4


# test ideas:
# good vision bad weather > high wind speed + slush
