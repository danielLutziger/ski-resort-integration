"""Tests for pick_recommendations()."""

from dataclasses import replace
from datetime import date, datetime
from zoneinfo import ZoneInfo

from custom_components.ski_resort_recommender.lib.models import (
    Connection,
    DayForecast,
    Forecasts,
    Resort,
    SnowRailOffer,
    WeatherPoint,
)
from custom_components.ski_resort_recommender.lib.scoring import score_day
from custom_components.ski_resort_recommender.lib.service import (
    SNOW_N_RAIL_TAG,
    RecommendationResult,
    RecommendationStatus,
    attach_connections,
    pick_recommendations,
)
from custom_components.ski_resort_recommender.lib.settings import Settings
from tests.scoring_values import SCORING

SATURDAY = date(2026, 11, 28)
SUNDAY = date(2026, 11, 29)
WEDNESDAY = date(2026, 11, 25)
TODAY = date(2026, 11, 24)  # Tuesday: the weekend is inside the 5 ranked days

WEEKEND = frozenset({5, 6})

SETTINGS = Settings(
    allowed_weekdays=WEEKEND,
    max_results=3,
    min_good_score=50.0,
    ranking_days=5,
    outlook_days=7,
    show_outlook=True,
    scoring=SCORING,
)


MAIN = "main"


def make_point(name: str = MAIN, weight: float = 1) -> WeatherPoint:
    """Create a weather point."""
    return WeatherPoint(name=name, lat=46.8, lon=9.3, elevation_m=2000, weight=weight)


def make_resort(key: str, *points: WeatherPoint, price: float | None = None) -> Resort:
    """Create a resort; without points it gets one point called MAIN."""
    return Resort(
        key=key,
        name=key,
        points=points or (make_point(),),
        meteoswiss_point_id=None,
        station="Chur",
        day_price_chf=price,
    )


def pick(
    resorts: list[Resort],
    forecasts: dict[str, list[DayForecast]],
    settings: Settings,
    *,
    today: date,
) -> RecommendationResult:
    """Call pick_recommendations for resorts that only have the MAIN point."""
    per_point: Forecasts = {key: {MAIN: days} for key, days in forecasts.items()}
    return pick_recommendations(resorts, per_point, settings, today=today)


def make_day(
    day: date,
    *,
    sun: float = 8,
    snow: float = 10,
    gust: float = 20,
    temp: float = -5,
    code: int = 0,
    hourly_codes: tuple[int, ...] = (),
    rain: float | None = None,
    visibility: float | None = None,
) -> DayForecast:
    """Create a forecast for day (snow = fresh snow before opening)."""
    return DayForecast(
        day=day,
        temp_min_c=temp - 4,
        temp_max_c=temp + 2,
        snowfall_cm=0,
        sunshine_hours=sun,
        daylight_hours=9,
        weather_code=code,
        visibility_m=visibility,
        temp_ski_c=temp,
        gust_max_kmh=gust,
        fresh_snow_cm=snow,
        snow_depth_cm=100,
        weather_codes_ski=hourly_codes,
        recent_rain_mm=rain,
    )


def make_rainy_day(day: date) -> DayForecast:
    """Create a rainy, windy, warm day."""
    return make_day(day, sun=0, snow=0, gust=70, temp=6, code=63)


def test_only_allowed_weekedays_are_returned() -> None:
    """A Wednesday is dropped when only weekends are allowed."""
    resort = make_resort("flims_laax")
    forecasts = {"flims_laax": [make_day(WEDNESDAY), make_day(SATURDAY)]}

    result = pick([resort], forecasts, SETTINGS, today=TODAY)

    days = [r.day.day for r in result.recommendations]

    assert days == [SATURDAY]


def test_same_resort_can_appear_twice() -> None:
    """One resort can be recommended for two different days."""
    resort = make_resort("laax")
    forecasts = {"laax": [make_day(SATURDAY), make_day(SUNDAY)]}

    result = pick([resort], forecasts, SETTINGS, today=TODAY)

    assert [r.resort.key for r in result.recommendations] == ["laax", "laax"]


def test_results_are_sorted_best_first_and_limited() -> None:
    """Results are sorted by score and cut to max_results."""
    resorts = [make_resort("a"), make_resort("b"), make_resort("c")]
    forecasts = {
        "a": [make_day(SATURDAY, sun=2), make_day(SUNDAY, sun=4)],
        "b": [make_day(SATURDAY, sun=8), make_day(SUNDAY, sun=6)],
        "c": [make_day(SATURDAY, sun=1)],
    }

    result = pick(resorts, forecasts, SETTINGS, today=TODAY)

    assert len(result.recommendations) == 3
    totals = [r.score.total for r in result.recommendations]
    assert totals == sorted(totals, reverse=True)
    assert result.recommendations[0].resort.key == "b"


def test_rainy_weekend_still_returns_entries_but_no_good_day() -> None:
    """Bad days are still listed, but none is good."""
    resort = make_resort("laax")
    forecasts = {"laax": [make_rainy_day(SATURDAY), make_rainy_day(SUNDAY)]}

    result = pick([resort], forecasts, SETTINGS, today=TODAY)

    assert len(result.recommendations) == 2
    assert result.has_good_day is False


def test_good_day_is_flagged() -> None:
    """A sunny cold day with fresh snow is good."""
    resort = make_resort("laax")
    forecasts = {"laax": [make_day(SATURDAY)]}

    result = pick([resort], forecasts, SETTINGS, today=TODAY)

    assert result.has_good_day is True


def test_no_go_weather_is_never_good_even_with_high_score() -> None:
    """A NO_GO weather code is never good."""
    resort = make_resort("laax")
    # perfect values for sun/snow/wind/temp, but thunderstorm code
    forecasts = {"laax": [make_day(SATURDAY, code=95)]}

    result = pick(
        [resort],
        forecasts,
        replace(SETTINGS, min_good_score=0.0),
        today=TODAY,
    )

    assert result.recommendations[0].is_good is False


def test_resort_without_forecast_is_skipped() -> None:
    """A resort missing from the forecasts does not crash."""
    resorts = [make_resort("laax"), make_resort("zermatt")]
    forecasts = {"laax": [make_day(SATURDAY)]}

    result = pick(resorts, forecasts, SETTINGS, today=TODAY)

    assert [r.resort.key for r in result.recommendations] == ["laax"]


def test_custom_weekdays_setting() -> None:
    """Only the configured weekdays are returned."""
    resort = make_resort("laax")
    forecasts = {"laax": [make_day(WEDNESDAY), make_day(SATURDAY)]}
    settings = replace(SETTINGS, allowed_weekdays=frozenset({2}))

    result = pick([resort], forecasts, settings, today=TODAY)

    assert [r.day.day for r in result.recommendations] == [WEDNESDAY]


def test_today_and_past_days_are_not_recommended() -> None:
    """Today itself is not recommended."""
    resort = make_resort("laax")
    forecasts = {"laax": [make_day(SATURDAY), make_day(SUNDAY)]}

    # today is the Saturday itself: only the Sunday is in the future
    result = pick([resort], forecasts, SETTINGS, today=SATURDAY)

    assert [r.day.day for r in result.recommendations] == [SUNDAY]


def test_past_days_are_not_recommended() -> None:
    """Days before today are not recommended."""
    resort = make_resort("laax")
    forecasts = {"laax": [make_day(SATURDAY)]}

    result = pick([resort], forecasts, SETTINGS, today=date(2026, 12, 1))

    assert result.recommendations == ()


def make_empty_day(day: date) -> DayForecast:
    """Create a day beyond the model horizon: every value is None."""
    return DayForecast(
        day=day,
        temp_min_c=None,
        temp_max_c=None,
        snowfall_cm=None,
        sunshine_hours=None,
        daylight_hours=9,
        weather_code=None,
        visibility_m=None,
        temp_ski_c=None,
        gust_max_kmh=None,
        fresh_snow_cm=None,
    )


def test_days_without_forecast_data_are_skipped() -> None:
    """Days beyond the model horizon give 'no forecast'."""
    forecasts = {"laax": [make_empty_day(SATURDAY), make_empty_day(SUNDAY)]}

    result = pick([make_resort("laax")], forecasts, SETTINGS, today=TODAY)

    assert result.recommendations == ()
    assert result.status is RecommendationStatus.NO_FORECAST


def test_empty_days_do_not_displace_real_days() -> None:
    """Empty days are skipped, real days stay."""
    forecasts = {"laax": [make_empty_day(SATURDAY), make_rainy_day(SUNDAY)]}

    result = pick([make_resort("laax")], forecasts, SETTINGS, today=TODAY)

    assert [r.day.day for r in result.recommendations] == [SUNDAY]


def test_status_good_day() -> None:
    """Status is GOOD_DAY when at least one day is good."""
    result = pick(
        [make_resort("laax")], {"laax": [make_day(SATURDAY)]}, SETTINGS, today=TODAY
    )

    assert result.status is RecommendationStatus.GOOD_DAY


def test_status_no_good_day_when_scored_but_poor() -> None:
    """Status is NO_GOOD_DAY when days are scored but poor."""
    result = pick(
        [make_resort("laax")],
        {"laax": [make_rainy_day(SATURDAY)]},
        SETTINGS,
        today=TODAY,
    )

    assert result.status is RecommendationStatus.NO_GOOD_DAY


def test_points_are_combined_by_weighted_average() -> None:
    """The resort score is the weighted average of its point scores."""
    sunny, cloudy = make_day(SATURDAY, sun=8), make_day(SATURDAY, sun=0)
    resort = make_resort("laax", make_point("top", weight=3), make_point("mid"))
    forecasts: Forecasts = {"laax": {"top": [sunny], "mid": [cloudy]}}

    result = pick_recommendations([resort], forecasts, SETTINGS, today=TODAY)

    expected = (
        3 * score_day(sunny, SCORING).total + score_day(cloudy, SCORING).total
    ) / 4
    assert result.recommendations[0].score.total == expected


def test_best_point_is_named() -> None:
    """The recommendation names the best point and shows its forecast."""
    sunny, cloudy = make_day(SATURDAY, sun=8), make_day(SATURDAY, sun=0)
    resort = make_resort("laax", make_point("top"), make_point("mid"))
    forecasts: Forecasts = {"laax": {"top": [cloudy], "mid": [sunny]}}

    (rec,) = pick_recommendations(
        [resort], forecasts, SETTINGS, today=TODAY
    ).recommendations

    assert rec.point.name == "mid"
    assert rec.day is sunny


def test_point_without_data_is_left_out_of_the_average() -> None:
    """A point beyond the horizon does not pull the resort score to 0."""
    sunny = make_day(SATURDAY)
    resort = make_resort("laax", make_point("top"), make_point("mid"))
    forecasts: Forecasts = {"laax": {"top": [sunny], "mid": [make_empty_day(SATURDAY)]}}

    (rec,) = pick_recommendations(
        [resort], forecasts, SETTINGS, today=TODAY
    ).recommendations

    assert rec.score.total == score_day(sunny, SCORING).total


def test_no_go_at_another_point_does_not_block_a_good_day() -> None:
    """Only the best point's weather decides NO_GO (one shower elsewhere is ok)."""
    resort = make_resort("laax", make_point("top"), make_point("mid"))
    forecasts: Forecasts = {
        "laax": {"top": [make_day(SATURDAY)], "mid": [make_day(SATURDAY, code=95)]}
    }
    settings = replace(SETTINGS, min_good_score=0.0)

    (rec,) = pick_recommendations(
        [resort], forecasts, settings, today=TODAY
    ).recommendations

    assert rec.point.name == "top"
    assert rec.is_good is True


def test_points_can_cover_different_days() -> None:
    """Each day is scored with the points that have data for it."""
    resort = make_resort("laax", make_point("top"), make_point("mid"))
    forecasts: Forecasts = {
        "laax": {"top": [make_day(SATURDAY)], "mid": [make_day(SUNDAY, sun=0)]}
    }

    result = pick_recommendations([resort], forecasts, SETTINGS, today=TODAY)

    assert [(r.day.day, r.point.name) for r in result.recommendations] == [
        (SATURDAY, "top"),
        (SUNDAY, "mid"),
    ]


MONDAY_AFTER = date(2026, 11, 30)  # today + 6
TUESDAY_AFTER = date(2026, 12, 1)  # today + 7
WEDNESDAY_AFTER = date(2026, 12, 2)  # today + 8
ALL_DAYS = replace(SETTINGS, allowed_weekdays=frozenset(range(7)))


def test_days_after_the_ranking_window_go_to_the_outlook() -> None:
    """Days 6-7 are not ranked; the best of them is the outlook entry."""
    forecasts = {
        "laax": [
            make_day(SATURDAY, sun=2),
            make_day(MONDAY_AFTER, sun=4),
            make_day(TUESDAY_AFTER, sun=8),
        ]
    }

    result = pick([make_resort("laax")], forecasts, ALL_DAYS, today=TODAY)

    assert [r.day.day for r in result.recommendations] == [SATURDAY]
    assert result.outlook is not None
    assert result.outlook.day.day == TUESDAY_AFTER


def test_days_after_the_outlook_window_are_ignored() -> None:
    """Nothing beyond outlook_days is shown."""
    forecasts = {"laax": [make_day(WEDNESDAY_AFTER)]}

    result = pick([make_resort("laax")], forecasts, ALL_DAYS, today=TODAY)

    assert result.recommendations == ()
    assert result.outlook is None


def test_outlook_respects_allowed_weekdays() -> None:
    """A great outlook day on a disallowed weekday is not shown."""
    forecasts = {"laax": [make_day(MONDAY_AFTER, sun=8)]}

    result = pick([make_resort("laax")], forecasts, SETTINGS, today=TODAY)

    assert result.outlook is None


def test_outlook_alone_does_not_change_the_status() -> None:
    """Only ranked days count for the headline: outlook only -> no forecast yet."""
    sunday = date(2026, 11, 29)
    forecasts = {"laax": [make_day(sunday)]}

    # seen from Sunday 22.11: next Sunday is day 7, so outlook only
    result = pick([make_resort("laax")], forecasts, SETTINGS, today=date(2026, 11, 22))

    assert result.recommendations == ()
    assert result.outlook is not None
    assert result.status is RecommendationStatus.NO_FORECAST


def test_scoring_settings_are_used_by_the_service() -> None:
    """pick_recommendations scores with settings.scoring."""
    forecasts = {"laax": [make_day(SATURDAY, sun=8)]}
    doubled_sun = replace(SETTINGS, scoring=replace(SCORING, sun_points=70))

    normal = pick([make_resort("laax")], forecasts, SETTINGS, today=TODAY)
    sunnier = pick([make_resort("laax")], forecasts, doubled_sun, today=TODAY)

    gain = (
        sunnier.recommendations[0].score.total - normal.recommendations[0].score.total
    )
    assert gain == 30


def test_a_short_shower_does_not_block_a_good_day() -> None:
    """Only rain in several ski hours makes a day NO_GO."""
    shower = make_day(SATURDAY, code=63, hourly_codes=(63, 0, 0, 0, 0, 0, 0, 0))

    (rec,) = pick(
        [make_resort("laax")], {"laax": [shower]}, SETTINGS, today=TODAY
    ).recommendations

    assert rec.is_good is True


def test_icy_slope_after_rain_is_not_good() -> None:
    """Rain before opening makes a sunny powder day not good."""
    icy = make_day(SATURDAY, rain=5)

    (rec,) = pick(
        [make_resort("laax")], {"laax": [icy]}, SETTINGS, today=TODAY
    ).recommendations

    assert rec.is_good is False


def make_connection(minutes: int, day: date = SATURDAY) -> Connection:
    """Create a morning connection that takes the given number of minutes."""
    zurich = ZoneInfo("Europe/Zurich")
    return Connection(
        departure=datetime(day.year, day.month, day.day, 7, 0, tzinfo=zurich),
        platform="9",
        arrival=datetime(day.year, day.month, day.day, 9, 0, tzinfo=zurich),
        duration_min=minutes,
        transfers=1,
        legs=(),
    )


def travel_points(result: RecommendationResult) -> dict[str, float]:
    """Travel reason per resort key."""
    return {r.resort.key: r.score.reasons["travel"] for r in result.recommendations}


def test_travel_points_are_relative_shortest_10_longest_0() -> None:
    """Shortest trip gets travel_points, longest 0, linear by travel time."""
    resorts = [make_resort(k) for k in ("near", "far", "mid")]
    forecasts = {k: [make_day(SATURDAY)] for k in ("near", "far", "mid")}
    travel = {
        "near": make_connection(60),
        "far": make_connection(180),
        "mid": make_connection(120),
    }

    result = pick_recommendations(
        resorts,
        {k: {MAIN: v} for k, v in forecasts.items()},
        SETTINGS,
        today=TODAY,
        travel=travel,
    )

    assert travel_points(result) == {"near": 10, "mid": 5, "far": 0}
    assert [r.resort.key for r in result.recommendations] == ["near", "mid", "far"]


def test_resort_without_morning_connection_gets_no_travel_points() -> None:
    """No connection in the arrival window: 0 travel points, no connection shown."""
    resorts = [make_resort("train"), make_resort("no_train")]
    forecasts = {k: {MAIN: [make_day(SATURDAY)]} for k in ("train", "no_train")}

    result = pick_recommendations(
        resorts,
        forecasts,
        SETTINGS,
        today=TODAY,
        travel={"train": make_connection(90)},
    )

    by_key = {r.resort.key: r for r in result.recommendations}
    assert by_key["train"].score.reasons["travel"] == 10
    assert by_key["no_train"].score.reasons["travel"] == 0
    assert by_key["no_train"].connection is None


def test_without_travel_data_every_resort_gets_0_travel_points() -> None:
    """No home station set: travel does not change the ranking."""
    result = pick(
        [make_resort("laax")], {"laax": [make_day(SATURDAY)]}, SETTINGS, today=TODAY
    )

    assert result.recommendations[0].score.reasons["travel"] == 0


def test_attach_connections_shows_the_connection_of_the_ski_day() -> None:
    """The reference connection is replaced by the one of the recommended day."""
    resorts = [make_resort("laax")]
    result = pick_recommendations(
        resorts,
        {"laax": {MAIN: [make_day(SATURDAY)]}},
        SETTINGS,
        today=TODAY,
        travel={"laax": make_connection(90, day=SUNDAY)},
    )
    exact = make_connection(95)

    updated = attach_connections(result, {("laax", SATURDAY): exact})

    assert updated.recommendations[0].connection is exact


def price_points(result: RecommendationResult) -> dict[str, float]:
    """Price reason per resort key."""
    return {r.resort.key: r.score.reasons["price"] for r in result.recommendations}


def test_price_points_are_relative_cheapest_5_most_expensive_0() -> None:
    """Day price from the resort file: cheapest price_points, most expensive 0."""
    resorts = [
        make_resort("cheap", price=60),
        make_resort("mid", price=80),
        make_resort("dear", price=100),
    ]
    forecasts = {k: {MAIN: [make_day(SATURDAY)]} for k in ("cheap", "mid", "dear")}

    result = pick_recommendations(resorts, forecasts, SETTINGS, today=TODAY)

    assert price_points(result) == {"cheap": 5, "mid": 2.5, "dear": 0}


def test_resort_without_price_gets_no_price_points() -> None:
    """Unknown price: 0 price points (like a missing train connection)."""
    resorts = [make_resort("known", price=70), make_resort("unknown")]
    forecasts = {k: {MAIN: [make_day(SATURDAY)]} for k in ("known", "unknown")}

    result = pick_recommendations(resorts, forecasts, SETTINGS, today=TODAY)

    assert price_points(result) == {"known": 5, "unknown": 0}


def test_live_prices_override_the_static_prices() -> None:
    """A prices dict (e.g. from a live source later) replaces day_price_chf."""
    resorts = [make_resort("a", price=60), make_resort("b", price=100)]
    forecasts = {k: {MAIN: [make_day(SATURDAY)]} for k in ("a", "b")}

    result = pick_recommendations(
        resorts, forecasts, SETTINGS, today=TODAY, prices={"a": 120, "b": 90}
    )

    assert price_points(result) == {"a": 0, "b": 5}


def test_travel_and_price_count_towards_a_good_day() -> None:
    """is_good uses the final total: weather 58 + travel 10 + price 5 is good."""
    day = make_day(SATURDAY, sun=8, snow=0)  # weather part: sun 40 + depth 20
    resorts = [make_resort("near", price=60), make_resort("far", price=100)]
    forecasts = {k: {MAIN: [day]} for k in ("near", "far")}
    settings = replace(SETTINGS, min_good_score=65)

    result = pick_recommendations(
        resorts,
        forecasts,
        settings,
        today=TODAY,
        travel={"near": make_connection(60), "far": make_connection(180)},
    )

    good = {r.resort.key: r.is_good for r in result.recommendations}
    assert good == {"near": True, "far": False}


def test_resorts_with_a_snow_n_rail_offer_get_the_tag() -> None:
    """Tag "snow-n-rail" for resorts with an offer (availability: issue #19)."""
    offer = SnowRailOffer(offer="snownrail-pizol", up_to_pct=30)
    resorts = [replace(make_resort("pizol"), snow_n_rail=offer), make_resort("other")]
    forecasts = {k: {MAIN: [make_day(SATURDAY)]} for k in ("pizol", "other")}

    result = pick_recommendations(resorts, forecasts, SETTINGS, today=TODAY)

    tags = {r.resort.key: r.tags for r in result.recommendations}
    assert tags == {"pizol": (SNOW_N_RAIL_TAG,), "other": ()}
    assert SNOW_N_RAIL_TAG == "snow-n-rail"


def test_all_results_hold_every_resort_day_sorted_with_outlook_flag() -> None:
    """result.all: every allowed resort-day up to outlook_days, best first."""
    forecasts = {
        "laax": [make_day(SATURDAY, sun=8), make_day(SUNDAY, sun=2)],
        "flims": [make_day(SATURDAY, sun=5), make_day(date(2026, 11, 30), sun=8)],
    }
    settings = replace(SETTINGS, allowed_weekdays=frozenset(range(7)), max_results=1)

    result = pick(
        [make_resort("laax"), make_resort("flims")], forecasts, settings, today=TODAY
    )

    assert len(result.recommendations) == 1
    assert len(result.all) == 4
    totals = [r.score.total for r in result.all]
    assert totals == sorted(totals, reverse=True)
    outlook_days = {(r.resort.key, r.day.day) for r in result.all if r.outlook}
    assert outlook_days == {("flims", date(2026, 11, 30))}  # today + 6


def test_every_result_keeps_its_point_scores() -> None:
    """Per-point forecast and score for the details view."""
    resort = make_resort("laax", make_point("top", weight=2), make_point("mid"))
    forecasts: Forecasts = {
        "laax": {"top": [make_day(SATURDAY, sun=8)], "mid": [make_day(SATURDAY, sun=0)]}
    }

    (rec,) = pick_recommendations(
        [resort], forecasts, SETTINGS, today=TODAY
    ).recommendations

    assert [(p.point.name, p.point.weight) for p in rec.points] == [
        ("top", 2),
        ("mid", 1),
    ]
    assert rec.points[0].score.total > rec.points[1].score.total
    assert rec.points[0].day.sunshine_hours == 8


def test_attach_connections_keeps_all_results() -> None:
    """The modal's list (result.all) survives attaching the exact connections."""
    forecasts = {
        "laax": [make_day(SATURDAY, sun=8), make_day(SUNDAY, sun=2)],
        "flims": [make_day(SATURDAY, sun=5)],
    }
    result = pick(
        [make_resort("laax"), make_resort("flims")], forecasts, SETTINGS, today=TODAY
    )
    exact = make_connection(95)

    updated = attach_connections(result, {("laax", SATURDAY): exact})

    assert len(updated.all) == len(result.all) == 3
    attached = [
        r for r in updated.all if r.resort.key == "laax" and r.day.day == SATURDAY
    ]
    assert attached[0].connection is exact


def test_outlook_is_hidden_when_switched_off() -> None:
    """show_outlook=False: no 4th entry; the modal list still has days 6-7."""
    forecasts = {"laax": [make_day(SATURDAY), make_day(date(2026, 11, 30))]}
    settings = replace(
        SETTINGS, allowed_weekdays=frozenset(range(7)), show_outlook=False
    )

    result = pick([make_resort("laax")], forecasts, settings, today=TODAY)

    assert result.outlook is None
    assert [r.outlook for r in result.all] == [False, True]


def test_outlook_is_off_by_default() -> None:
    """Default settings (weekends) do not show the outlook entry."""
    assert Settings().show_outlook is False
