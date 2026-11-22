"""Tests for score_day() and combine_scores()."""

from dataclasses import replace
from datetime import date

import pytest

from custom_components.ski_resort_recommender.lib.models import DayForecast
from custom_components.ski_resort_recommender.lib.scoring import (
    combine_scores,
    is_no_go,
    score_day,
)
from custom_components.ski_resort_recommender.lib.settings import ScoringSettings
from tests.scoring_values import SCORING

# sunny, calm, cold, no fresh snow, clear view: only the sun scores (60)
CLEAR_DAY = DayForecast(
    day=date(2026, 12, 5),
    temp_min_c=-10,
    temp_max_c=-3,
    snowfall_cm=0,
    sunshine_hours=8,
    daylight_hours=9,
    weather_code=0,
    visibility_m=20_000,
    temp_ski_c=-5,
    gust_max_kmh=20,
    fresh_snow_cm=0,
)


def test_defaults_are_the_documented_values() -> None:
    """Changing a default weight must be a visible decision (update SCORING too)."""
    assert ScoringSettings() == SCORING


def test_clear_day_without_penalties_scores_the_sun_points() -> None:
    """Sun is the only positive part on a day without fresh snow."""
    score = score_day(CLEAR_DAY, SCORING)

    assert score.total == 60
    assert score.reasons == {
        "sun": 60,
        "snow": 0,
        "wind": 0,
        "temp": 0,
        "weather": 0,
        "visibility": 0,
        "icy": 0,
    }


def test_bluebird_powder_day_is_the_top_of_the_scale() -> None:
    """Full sun after 30 cm of fresh snow (48 h before opening) scores 100."""
    bluebird = replace(CLEAR_DAY, fresh_snow_cm=30)

    assert score_day(bluebird, SCORING).total == 100


def test_bluebird_day_beats_sun_without_snow_and_snow_without_sun() -> None:
    """The sunny day after the storm ranks above both alternatives."""
    bluebird = replace(CLEAR_DAY, fresh_snow_cm=25)
    old_snow = CLEAR_DAY
    snowing = replace(
        CLEAR_DAY,
        sunshine_hours=0,
        weather_code=75,
        snowfall_cm=25,
        fresh_snow_cm=25,
        visibility_m=400,
    )

    best = score_day(bluebird, SCORING).total
    assert best > score_day(old_snow, SCORING).total
    assert best > score_day(snowing, SCORING).total


def test_sun_is_measured_against_day_length() -> None:
    """80 % of daylight gives full points, 40 % gives half."""
    full = replace(CLEAR_DAY, sunshine_hours=7.2, daylight_hours=9)
    half = replace(CLEAR_DAY, sunshine_hours=3.6, daylight_hours=9)

    assert score_day(full, SCORING).reasons["sun"] == pytest.approx(60)
    assert score_day(half, SCORING).reasons["sun"] == pytest.approx(30)


def test_fresh_snow_scales_up_to_snow_full_cm() -> None:
    """Half of snow_full_cm gives half the snow points, more is capped."""
    half = replace(CLEAR_DAY, fresh_snow_cm=15)
    lots = replace(CLEAR_DAY, fresh_snow_cm=80)

    assert score_day(half, SCORING).reasons["snow"] == 20
    assert score_day(lots, SCORING).reasons["snow"] == 40


def test_snowfall_codes_are_not_penalised() -> None:
    """Snowing today counts via visibility, not via the weather class."""
    snowing = replace(CLEAR_DAY, weather_code=75)

    assert score_day(snowing, SCORING).reasons["weather"] == 0


def test_clear_day_beats_rainy_day() -> None:
    """Rain is NO_GO."""
    rainy = replace(CLEAR_DAY, weather_code=63)

    assert score_day(CLEAR_DAY, SCORING).total > score_day(rainy, SCORING).total


@pytest.mark.parametrize(
    ("gust", "points"), [(None, 0), (30, 0), (40, 0), (60, -15), (80, -30), (130, -30)]
)
def test_gust_penalty_is_linear_and_capped(gust: float | None, points: float) -> None:
    """No penalty up to 40 km/h, full (capped) penalty from 80 km/h."""
    windy = replace(CLEAR_DAY, gust_max_kmh=gust)

    assert score_day(windy, SCORING).reasons["wind"] == points


@pytest.mark.parametrize(
    ("temp", "points"),
    [(None, 0), (-20, -10), (-15, 0), (-5, 0), (2, 0), (4, -10), (6, -20), (10, -20)],
)
def test_temperature_is_a_penalty_only(temp: float | None, points: float) -> None:
    """Ski-hours mean: 0 from -15 to +2 °C, slush penalty up to +6 °C, cold below."""
    day = replace(CLEAR_DAY, temp_ski_c=temp)

    assert score_day(day, SCORING).reasons["temp"] == points


def test_fog_scores_lower_than_clear_view() -> None:
    """Low visibility during ski hours costs points."""
    foggy = replace(CLEAR_DAY, visibility_m=300)

    assert score_day(foggy, SCORING).total < score_day(CLEAR_DAY, SCORING).total


def test_visibility_penalty_scales_between_thresholds() -> None:
    """No penalty at 5 km or more, full penalty at 1 km or less, linear between."""
    points = {
        v: score_day(replace(CLEAR_DAY, visibility_m=v), SCORING).reasons["visibility"]
        for v in (20_000, 5_000, 3_000, 1_000, 200)
    }

    assert points == {20_000: 0, 5_000: 0, 3_000: -15, 1_000: -30, 200: -30}


def test_unknown_visibility_is_neutral() -> None:
    """Beyond the visibility horizon there is no penalty."""
    unknown = replace(CLEAR_DAY, visibility_m=None)

    assert score_day(unknown, SCORING).reasons["visibility"] == 0


def test_bad_weather_good_view_beats_good_weather_bad_view() -> None:
    """Snowfall with a clear view beats a dry day in the fog."""
    snowing_clear_view = replace(CLEAR_DAY, weather_code=73, visibility_m=20_000)
    dry_in_fog = replace(CLEAR_DAY, weather_code=3, visibility_m=300)

    assert (
        score_day(snowing_clear_view, SCORING).total
        > score_day(dry_in_fog, SCORING).total
    )


def test_settings_change_the_points() -> None:
    """Every part reads its numbers from ScoringSettings."""
    day = replace(CLEAR_DAY, weather_code=45, gust_max_kmh=60, temp_ski_c=4)
    scoring = replace(
        SCORING,
        sun_points=50,
        weather_bad_points=-40,
        gust_limit_kmh=60,
        temp_slush_start_c=4,
    )

    reasons = score_day(day, scoring).reasons

    assert reasons["sun"] == 50
    assert reasons["weather"] == -40
    assert reasons["wind"] == 0
    assert reasons["temp"] == 0


def test_combine_scores_is_a_weighted_average() -> None:
    """Total and every reason are averaged with the point weights."""
    good = score_day(CLEAR_DAY, SCORING)
    bad = score_day(replace(CLEAR_DAY, sunshine_hours=0), SCORING)

    combined = combine_scores([(3, good), (1, bad)])

    assert combined.total == (3 * good.total + bad.total) / 4
    assert combined.reasons["sun"] == (3 * good.reasons["sun"] + bad.reasons["sun"]) / 4


DRY = (0, 0, 0, 0, 0, 0, 0, 0)  # eight clear ski hours (09:00-16:00)
RAIN = 63


def test_weather_points_are_averaged_over_the_ski_hours() -> None:
    """One rain hour out of eight costs an eighth of the NO_GO points."""
    shower = replace(CLEAR_DAY, weather_code=RAIN, weather_codes_ski=(RAIN, *DRY[1:]))

    assert score_day(shower, SCORING).reasons["weather"] == -50 / 8
    assert is_no_go(shower, SCORING) is False


def test_rain_in_no_go_min_hours_makes_a_no_go_day() -> None:
    """Two rain hours (no_go_min_hours) are enough to rule the day out."""
    wet = replace(CLEAR_DAY, weather_codes_ski=(RAIN, RAIN, *DRY[2:]))

    assert is_no_go(wet, SCORING) is True


def test_daily_worst_code_alone_does_not_decide() -> None:
    """A rainy night (daily code 63) with dry ski hours is a normal day."""
    rainy_night = replace(CLEAR_DAY, weather_code=RAIN, weather_codes_ski=DRY)

    assert score_day(rainy_night, SCORING).reasons["weather"] == 0
    assert is_no_go(rainy_night, SCORING) is False


def test_daily_code_is_the_fallback_without_hourly_codes() -> None:
    """Without hourly codes the daily code decides, as before."""
    rainy = replace(CLEAR_DAY, weather_code=RAIN, weather_codes_ski=())

    assert score_day(rainy, SCORING).reasons["weather"] == -50
    assert is_no_go(rainy, SCORING) is True


@pytest.mark.parametrize(
    ("rain", "points"), [(None, 0), (0, 0), (0.5, 0), (2.75, -20), (5, -40), (20, -40)]
)
def test_rain_before_opening_means_an_icy_slope(
    rain: float | None, points: float
) -> None:
    """Rain in the 48 h before opening refreezes: penalty from 0.5 mm, full at 5 mm."""
    day = replace(CLEAR_DAY, recent_rain_mm=rain)

    assert score_day(day, SCORING).reasons["icy"] == points


def test_sunny_day_after_rain_is_not_good() -> None:
    """Sun on an icy slope stays below min_good_score (60)."""
    icy = replace(CLEAR_DAY, recent_rain_mm=5)

    assert score_day(icy, SCORING).total < 60


@pytest.mark.parametrize(
    ("snow_on_top", "points"), [(None, -40), (0, -40), (10, -20), (20, 0), (35, 0)]
)
def test_snow_after_the_rain_covers_the_ice(
    snow_on_top: float | None, points: float
) -> None:
    """The icy penalty shrinks with the snow on top, gone from ice_cover_full_cm."""
    day = replace(CLEAR_DAY, recent_rain_mm=5, snow_after_rain_cm=snow_on_top)

    assert score_day(day, SCORING).reasons["icy"] == points


def test_bluebird_day_on_covered_ice_is_still_the_top() -> None:
    """Rain, then 30 cm of snow, then sun: full points, the ice is buried."""
    day = replace(CLEAR_DAY, recent_rain_mm=10, fresh_snow_cm=30, snow_after_rain_cm=30)

    assert score_day(day, SCORING).total == 100


# test ideas:
# good vision bad weather > high wind speed + slush
