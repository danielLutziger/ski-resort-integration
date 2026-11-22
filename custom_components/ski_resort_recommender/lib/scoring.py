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

    # TODO: one resort multiple weather points, so weather needs a different scoring
    weather = _WEATHER_POINTS[classify(day.weather_code)]
    reasons = {"sun": sun, "snow": snow, "wind": wind, "temp": temp, "weather": weather}
    total = max(0.0, sum(reasons.values()))
    return DayScore(total, reasons=reasons)


def _temp_points(day: DayForecast) -> float:
    if day.temp_max_c is None:
        return 0.0
    if _TEMP_GOOD_MIN <= day.temp_max_c <= _TEMP_GOOD_MAX:
        return 20
    if day.temp_max_c > _TEMP_SLUSH:  # slush... we dislike slush
        return -10
    return 10
