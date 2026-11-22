"""User settings for the recommendation."""

from dataclasses import dataclass

SATURDAY = 5
SUNDAY = 6


@dataclass(frozen=True, slots=True)
class ScoringSettings:
    """Weights and thresholds of score_day(); flat numbers for the HA options."""

    # sun: up to sun_points, full points from sun_full_hours (cloudy skiing is ok)
    sun_points: float = 30
    sun_full_hours: float = 8
    # fresh snow: up to snow_points, full points from snow_full_cm
    snow_points: float = 20
    snow_full_cm: float = 25
    # wind: wind_penalty per wind_penalty_step_kmh above wind_limit_kmh
    # (village value; on the mountain up to 60 would be ok)
    wind_limit_kmh: float = 30
    wind_penalty: float = 25
    wind_penalty_step_kmh: float = 30
    # max temperature of the day: good band, ok, slush above temp_slush_c
    temp_good_min_c: float = -8
    temp_good_max_c: float = 2
    temp_slush_c: float = 5
    temp_good_points: float = 20
    temp_ok_points: float = 10
    temp_slush_points: float = -10
    # points per weather class (see weather_codes.py)
    weather_very_good_points: float = 0
    weather_neutral_points: float = 0
    weather_bad_points: float = -15
    weather_no_go_points: float = -50
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
