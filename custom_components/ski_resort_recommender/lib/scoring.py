"""Score one forecast day at one resort."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from custom_components.ski_resort_recommender.lib.settings import ScoringSettings
from custom_components.ski_resort_recommender.lib.weather_codes import (
    WeatherClass,
    classify,
)

if TYPE_CHECKING:
    from .models import DayForecast


@dataclass(frozen=True, slots=True)
class DayScore:
    """Total score of a day plus the points per reason."""

    total: float  # total score 0...100
    reasons: dict[str, float]  # HA card can explain result


def score_day(day: DayForecast, scoring: ScoringSettings | None = None) -> DayScore:
    """Score one day at one resort from 0 (skip) to 100 (bluebird powder day)."""
    s = scoring or ScoringSettings()
    reasons = {
        "sun": _sun_points(day, s),
        "snow": _ramp(day.fresh_snow_cm or 0, 0, s.snow_full_cm) * s.snow_points,
        "wind": -_ramp(day.gust_max_kmh or 0, s.gust_limit_kmh, s.gust_full_kmh)
        * s.wind_penalty,
        "temp": _temp_points(day, s),
        "weather": _weather_points(day, s),
        "visibility": _visibility_points(day, s),
        "icy": -_ramp(day.recent_rain_mm or 0, s.rain_limit_mm, s.rain_full_mm)
        * s.icy_penalty,
    }
    total = max(0.0, sum(reasons.values()))
    return DayScore(total, reasons=reasons)


def is_no_go(day: DayForecast, scoring: ScoringSettings | None = None) -> bool:
    """Rain, freezing rain or thunder in at least no_go_min_hours ski hours."""
    s = scoring or ScoringSettings()
    if not day.weather_codes_ski:
        return classify(day.weather_code) is WeatherClass.NO_GO
    no_go_hours = sum(
        classify(code) is WeatherClass.NO_GO for code in day.weather_codes_ski
    )
    return no_go_hours >= s.no_go_min_hours


def combine_scores(weighted: list[tuple[float, DayScore]]) -> DayScore:
    """Weighted average of several point scores (the total and every reason)."""
    total_weight = sum(weight for weight, _ in weighted)
    total = sum(weight * score.total for weight, score in weighted) / total_weight
    reasons = {
        key: sum(weight * score.reasons[key] for weight, score in weighted)
        / total_weight
        for key in weighted[0][1].reasons
    }
    return DayScore(total, reasons=reasons)


def _ramp(value: float, start: float, full: float) -> float:
    """0 up to start, 1 from full, linear in between."""
    return min(max((value - start) / (full - start), 0.0), 1.0)


def _sun_points(day: DayForecast, s: ScoringSettings) -> float:
    """Sunshine as a share of the daylight; full points from sun_full_share."""
    if not day.sunshine_hours or not day.daylight_hours:
        return 0.0
    share = day.sunshine_hours / day.daylight_hours
    return _ramp(share, 0, s.sun_full_share) * s.sun_points


def _temp_points(day: DayForecast, s: ScoringSettings) -> float:
    """Penalty for slush (growing) or deep cold; unknown temperature is neutral."""
    if day.temp_ski_c is None:
        return 0.0
    if day.temp_ski_c < s.temp_cold_c:
        return -s.temp_cold_penalty
    slush = _ramp(day.temp_ski_c, s.temp_slush_start_c, s.temp_slush_full_c)
    return -slush * s.temp_slush_penalty


def _weather_points(day: DayForecast, s: ScoringSettings) -> float:
    """Class points averaged over the ski hours (daily code if no hourly codes)."""
    points = {
        WeatherClass.VERY_GOOD: s.weather_very_good_points,
        WeatherClass.NEUTRAL: s.weather_neutral_points,
        WeatherClass.BAD: s.weather_bad_points,
        WeatherClass.NO_GO: s.weather_no_go_points,
    }
    codes = day.weather_codes_ski or (day.weather_code,)
    return sum(points[classify(code)] for code in codes) / len(codes)


def _visibility_points(day: DayForecast, s: ScoringSettings) -> float:
    """Penalty for fog / flat light; unknown visibility counts as neutral."""
    if day.visibility_m is None:
        return 0.0
    # ramp from good (no penalty) down to bad (full penalty)
    share_bad = _ramp(-day.visibility_m, -s.visibility_good_m, -s.visibility_bad_m)
    return -share_bad * s.visibility_penalty
