"""User settings for the recommendation."""

from dataclasses import dataclass
from datetime import time

SATURDAY = 5
SUNDAY = 6


@dataclass(frozen=True, slots=True)
class ScoringSettings:
    """Weights and thresholds of score_day(); flat numbers for the HA options."""

    # sun: up to sun_points, full points from sun_full_share of the daylight
    sun_points: float = 40
    sun_full_share: float = 0.8
    # fresh snow (48 h before opening): up to snow_points, full from snow_full_cm
    snow_points: float = 25
    snow_full_cm: float = 30
    # snow depth (base) at opening, all season: 0 up to snow_depth_min_cm, full
    # snow_depth_points from snow_depth_full_cm
    snow_depth_points: float = 20
    snow_depth_min_cm: float = 20
    snow_depth_full_cm: float = 100
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
    # rain (mm) in the 48 h before opening refreezes into an icy slope: no penalty
    # up to rain_limit_mm (traces), full icy_penalty from rain_full_mm
    rain_limit_mm: float = 0.5
    rain_full_mm: float = 5
    icy_penalty: float = 40
    # snow that fell after the rain covers the ice: the penalty shrinks and is gone
    # from ice_cover_full_cm
    ice_cover_full_cm: float = 20
    # visibility in ski hours (WMO: fog below 1 km, mist 1-5 km): no penalty from
    # visibility_good_m up, full penalty from visibility_bad_m down
    visibility_good_m: float = 5000
    visibility_bad_m: float = 1000
    visibility_penalty: float = 30
    # travel time by train, relative: shortest trip travel_points, longest 0
    travel_points: float = 10
    # day ticket price, relative: cheapest resort price_points, most expensive 0
    price_points: float = 5


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
    # public transport from home: None = no travel score and no connections
    home_station: str | None = None
    # the morning connection must arrive in this window; closest to the target wins
    arrival_target: time = time(9, 0)
    arrival_earliest: time = time(8, 45)
    arrival_latest: time = time(9, 30)
    # no night trips: the morning connection must not leave before this
    departure_earliest: time = time(5, 0)
