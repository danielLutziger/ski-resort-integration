"""Tests for the season dates: closed resorts are listed but never recommended."""

from dataclasses import replace
from datetime import date

import pytest

from custom_components.ski_resort_recommender.lib.models import Resort, Season
from custom_components.ski_resort_recommender.lib.service import (
    RecommendationResult,
    RecommendationStatus,
    pick_recommendations,
)
from tests.test_service import (
    MAIN,
    SATURDAY,
    SETTINGS,
    SUNDAY,
    TODAY,
    make_day,
    make_point,
    make_resort,
)

SEASON = Season(
    start=date(2026, 11, 28),
    end=date(2027, 4, 4),
    daily_from=date(2026, 12, 5),
    full_from=date(2026, 12, 19),
)


@pytest.mark.parametrize(
    ("day", "is_open"),
    [
        (date(2026, 11, 27), False),  # the day before the start
        (date(2026, 11, 28), True),  # first Saturday
        (date(2026, 11, 30), False),  # Monday: weekends only before daily_from
        (date(2026, 12, 6), True),
        (date(2026, 12, 7), True),  # Monday after daily_from
        (date(2027, 4, 4), True),  # last day
        (date(2027, 4, 5), False),
        (date(2027, 12, 4), True),  # dates of last winter: outdated, ignored
    ],
)
def test_season_open_days(day: date, *, is_open: bool) -> None:
    """Start and end count as open; before daily_from only Saturday and Sunday."""
    assert SEASON.is_open(day) is is_open


def test_without_daily_from_every_day_of_the_season_is_open() -> None:
    """Weekends only applies only when the file says so."""
    assert replace(SEASON, daily_from=None).is_open(date(2026, 11, 30))


def pick(resort: Resort, *days: date) -> RecommendationResult:
    """Rank the given days of one resort (every point has the same forecast)."""
    forecasts = {
        resort.key: {p.name: [make_day(d) for d in days] for p in resort.points}
    }
    return pick_recommendations([resort], forecasts, SETTINGS, today=TODAY)


def test_closed_resort_is_listed_last_but_never_recommended() -> None:
    """Not open yet: no recommendation, not good, still in the full list."""
    opened = replace(make_resort("laax"), season=SEASON)
    closed = replace(
        make_resort("frutt"), season=replace(SEASON, start=date(2026, 12, 5))
    )
    forecasts = {
        "laax": {MAIN: [make_day(SATURDAY, sun=1)]},
        "frutt": {MAIN: [make_day(SATURDAY, sun=9)]},  # better weather, but closed
    }

    result = pick_recommendations([closed, opened], forecasts, SETTINGS, today=TODAY)

    assert [r.resort.key for r in result.recommendations] == ["laax"]
    assert [(r.resort.key, r.closed) for r in result.all] == [
        ("laax", False),
        ("frutt", True),
    ]
    assert result.all[1].is_good is False


def test_only_closed_resorts_is_not_a_missing_forecast() -> None:
    """The headline tells closed resorts apart from no forecast."""
    closed = replace(
        make_resort("frutt"), season=replace(SEASON, start=date(2026, 12, 5))
    )

    result = pick(closed, SATURDAY)

    assert result.recommendations == ()
    assert result.status is RecommendationStatus.ALL_CLOSED


def test_unknown_season_counts_as_open() -> None:
    """No season in the file: nothing is filtered."""
    assert pick(make_resort("laax"), SATURDAY).recommendations[0].closed is False


def test_a_closed_day_does_not_become_the_outlook() -> None:
    """The outlook is a recommendation too (weekdays allowed, Monday closed)."""
    monday = date(2026, 11, 30)  # after the 5 ranked days: an outlook day
    every_day = replace(SETTINGS, allowed_weekdays=frozenset(range(7)))
    weekends_only = replace(make_resort("laax"), season=SEASON)
    forecasts = {"laax": {MAIN: [make_day(monday)]}}

    result = pick_recommendations([weekends_only], forecasts, every_day, today=TODAY)

    assert result.outlook is None
    assert [(r.day.day, r.closed) for r in result.all] == [(monday, True)]


def test_points_that_open_later_do_not_count() -> None:
    """Grindelwald opens 28.11, First 19.12: First is no part of the score."""
    first = replace(make_point("First"), opens=date(2026, 12, 19))
    resort = replace(make_resort("g", make_point("Scheidegg"), first), season=SEASON)
    forecasts = {
        "g": {
            "Scheidegg": [make_day(SUNDAY, sun=2)],
            "First": [make_day(SUNDAY, sun=9)],  # best weather, not open yet
        }
    }

    (r,) = pick_recommendations(
        [resort], forecasts, SETTINGS, today=TODAY
    ).recommendations

    assert r.point.name == "Scheidegg"
    assert [p.point.name for p in r.points] == ["Scheidegg"]


def test_no_open_point_means_closed() -> None:
    """Inside the season but every sector opens later."""
    later = replace(make_point("First"), opens=date(2026, 12, 19))
    resort = replace(make_resort("g", later), season=SEASON)

    result = pick(resort, SUNDAY)

    assert result.recommendations == ()
    assert result.all[0].closed is True
