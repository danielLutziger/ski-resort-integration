from dataclasses import dataclass

from custom_components.ski_resort_recommender.lib.weather_codes import (
    WeatherClass,
    classify,
)

from .models import DayForecast

_WEATHER_POINTS = {
    WeatherClass.VERY_GOOD: 0.0,
    WeatherClass.NEUTRAL: 0.0,
    WeatherClass.BAD: -15.0,
    WeatherClass.NO_GO: -50.0,
}


@dataclass(frozen=True, slots=True)
class DayScore:
    total: float  # total score 0...100
    reasons: dict[str, float]  # HA card can explain result


def score_day(day: DayForecast) -> DayScore:
    """Score one day at one resort from 0 (skipto 100 (perfect)."""
    sun = (
        min((day.sunshine_hours or 0) / 8, 1.0) * 30
    )  # we give it 30 points (cloudy skiing is ok)
    snow = (
        min((day.snowfall_cm or 0) / 25, 1.0) * 20
    )  # fresh snow up to 20 points (25cm snow is ok)
    wind = (
        -max(((day.wind_max_kmh or 0) - 30) / 30, 0.0) * 25
    )  # wind gets 30 points (30kmh wind is ok - this is for the village, on the mountains itself up to 60 would be ok)
    temp = _temp_points(day)

    # TODO: one resort multiple weather points, so weather needs a different scoring
    weather = _WEATHER_POINTS[classify(day.weather_code)]
    reasons = {"sun": sun, "snow": snow, "wind": wind, "temp": temp, "weather": weather}
    total = max(0.0, sum(reasons.values()))
    return DayScore(total, reasons=reasons)


def _temp_points(day: DayForecast) -> float:
    if day.temp_max_c is None:
        return 0.0
    elif -8 <= day.temp_max_c <= 2:
        return 20
    elif day.temp_max_c > 5:  # slush... we dislike slush
        return -10
    return 10
