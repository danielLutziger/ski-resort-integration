"""Score one forecast day at one resort."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from custom_components.ski_resort_recommender.lib.weather_codes import (
    WeatherClass,
    classify,
)

if TYPE_CHECKING:
    from .models import DayForecast

_WEATHER_POINTS = {
    WeatherClass.VERY_GOOD: 0.0,
    WeatherClass.NEUTRAL: 0.0,
    WeatherClass.BAD: -15.0,
    WeatherClass.NO_GO: -50.0,
}

# temperature band (max temperature of the day, °C)
_TEMP_GOOD_MIN = -8
_TEMP_GOOD_MAX = 2
_TEMP_SLUSH = 5

# visibility during ski hours (WMO: fog below 1 km, mist 1-5 km)
_VISIBILITY_GOOD_M = 5000  # no penalty from here up
_VISIBILITY_BAD_M = 1000  # full penalty from here down
_VISIBILITY_PENALTY = 30  # more than a BAD weather class: you can't see the piste


@dataclass(frozen=True, slots=True)
class DayScore:
    """Total score of a day plus the points per reason."""

    total: float  # total score 0...100
    reasons: dict[str, float]  # HA card can explain result


def score_day(day: DayForecast) -> DayScore:
    """Score one day at one resort from 0 (skip) to 100 (perfect)."""
    # sun up to 30 points (cloudy skiing is ok)
    sun = min((day.sunshine_hours or 0) / 8, 1.0) * 30
    # fresh snow up to 20 points (25 cm snow is ok)
    snow = min((day.snowfall_cm or 0) / 25, 1.0) * 20
    # wind penalty above 30 km/h (village value; on the mountain up to 60 would be ok)
    wind = -max(((day.wind_max_kmh or 0) - 30) / 30, 0.0) * 25
    temp = _temp_points(day)
    visibility = _visibility_points(day)

    # TODO: one resort multiple weather points, so weather needs a different scoring
    weather = _WEATHER_POINTS[classify(day.weather_code)]
    reasons = {
        "sun": sun,
        "snow": snow,
        "wind": wind,
        "temp": temp,
        "weather": weather,
        "visibility": visibility,
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


def _temp_points(day: DayForecast) -> float:
    if day.temp_max_c is None:
        return 0.0
    if _TEMP_GOOD_MIN <= day.temp_max_c <= _TEMP_GOOD_MAX:
        return 20
    if day.temp_max_c > _TEMP_SLUSH:  # slush... we dislike slush
        return -10
    return 10


def _visibility_points(day: DayForecast) -> float:
    """Penalty for fog / flat light; unknown visibility counts as neutral."""
    if day.visibility_m is None:
        return 0.0
    share_bad = (_VISIBILITY_GOOD_M - day.visibility_m) / (
        _VISIBILITY_GOOD_M - _VISIBILITY_BAD_M
    )
    return -min(max(share_bad, 0.0), 1.0) * _VISIBILITY_PENALTY
