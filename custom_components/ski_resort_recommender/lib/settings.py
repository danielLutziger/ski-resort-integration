"""User settings for the recommendation."""

from dataclasses import dataclass

SATURDAY = 5
SUNDAY = 6


@dataclass(frozen=True, slots=True)
class ScoringSettings:
    """Weights and thresholds of score_day(); flat numbers for the HA options."""

    # sun: up to sun_points, full points from sun_full_share of the daylight
    sun_points: float = 60
    sun_full_share: float = 0.8
    # fresh snow (48 h before opening): up to snow_points, full from snow_full_cm
    snow_points: float = 40
    snow_full_cm: float = 30
    # gusts in ski hours: no penalty up to gust_limit_kmh, full wind_penalty from
    # gust_full_kmh (lifts start to close)
    gust_limit_kmh: float = 40
    gust_full_kmh: float = 80
    wind_penalty: float = 30
    # mean temperature in ski hours: no penalty from temp_cold_c to
    # temp_slush_start_c; slush penalty grows up to temp_slush_full_c
    temp_cold_c: float = -15
    temp_cold_penalty: float = 10
    temp_slush_start_c: float = 2
    temp_slush_full_c: float = 6
    temp_slush_penalty: float = 20
    # points per weather class (see weather_codes.py)
    weather_very_good_points: float = 0
    weather_neutral_points: float = 0
    weather_bad_points: float = -15
    weather_no_go_points: float = -50
    # a day is NO_GO (never good) with NO_GO weather in at least this many ski hours
    no_go_min_hours: int = 2
    # visibility in ski hours (WMO: fog below 1 km, mist 1-5 km): no penalty from
    # visibility_good_m up, full penalty from visibility_bad_m down
    visibility_good_m: float = 5000
    visibility_bad_m: float = 1000
    visibility_penalty: float = 30


@dataclass(frozen=True, slots=True)
class Settings:
    """Settings for recommendation."""

    allowed_weekdays: frozenset[int] = frozenset({SATURDAY, SUNDAY})
    max_results: int = 3
    # below this score the day is not considered a good day
    min_good_score: float = 60.0
    # days 1..ranking_days are ranked (visibility data reaches about 5 days)
    ranking_days: int = 5
    # the best day after the ranking window, up to outlook_days, is a 4th entry
    outlook_days: int = 7
    scoring: ScoringSettings = ScoringSettings()
