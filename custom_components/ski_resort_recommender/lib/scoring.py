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
    """Score one day at one resort from 0 (skip) to 100 (perfect)."""
    s = scoring or ScoringSettings()
    sun = min((day.sunshine_hours or 0) / s.sun_full_hours, 1.0) * s.sun_points
    snow = min((day.snowfall_cm or 0) / s.snow_full_cm, 1.0) * s.snow_points
    wind_over = max((day.wind_max_kmh or 0) - s.wind_limit_kmh, 0.0)
    wind = -wind_over / s.wind_penalty_step_kmh * s.wind_penalty
    reasons = {
        "sun": sun,
        "snow": snow,
        "wind": wind,
        "temp": _temp_points(day, s),
        "weather": _weather_points(day, s),
        "visibility": _visibility_points(day, s),
    }
    total = max(0.0, sum(reasons.values()))
    return DayScore(total, reasons=reasons)


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


def _temp_points(day: DayForecast, s: ScoringSettings) -> float:
    """Points for the max temperature: good band, ok, or slush."""
    if day.temp_max_c is None:
        return 0.0
    if s.temp_good_min_c <= day.temp_max_c <= s.temp_good_max_c:
        return s.temp_good_points
    if day.temp_max_c > s.temp_slush_c:  # slush... we dislike slush
        return s.temp_slush_points
    return s.temp_ok_points


def _weather_points(day: DayForecast, s: ScoringSettings) -> float:
    """Points for the weather class of the day's weather code."""
    return {
        WeatherClass.VERY_GOOD: s.weather_very_good_points,
        WeatherClass.NEUTRAL: s.weather_neutral_points,
        WeatherClass.BAD: s.weather_bad_points,
        WeatherClass.NO_GO: s.weather_no_go_points,
    }[classify(day.weather_code)]


def _visibility_points(day: DayForecast, s: ScoringSettings) -> float:
    """Penalty for fog / flat light; unknown visibility counts as neutral."""
    if day.visibility_m is None:
        return 0.0
    share_bad = (s.visibility_good_m - day.visibility_m) / (
        s.visibility_good_m - s.visibility_bad_m
    )
    return -min(max(share_bad, 0.0), 1.0) * s.visibility_penalty
