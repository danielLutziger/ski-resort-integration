from dataclasses import dataclass

from .models import DayForecast

# bad weather codes according to documentation
# https://open-meteo.com/en/docs
WEATHER_CODES = {
    "very_good": [
        0,  # clear sky
        1,  # mainly clear
    ],
    "good": [
        2,  # partly cloudy
        3,  # overcast
        71,  # slight snowfall
    ],
    "bad": [
        45,  # fog (cant see.)
        *range(73, 78),  # snowfall in general
        85,  # slight snow showers
    ],
    "nogo": [
        *range(50, 68),  # rain in different variants
        *range(80, 83),  # heavy rain showers
        *range(86, 100),  # heavy snowshowers and thunderstorm
    ],
}
# TODO: we also need vision scores (how far can you see - more important than weather)
_BAD_CODES = {
    *range(51, 68),
    *range(80, 83),
    *range(95, 100),
}  # rain, showers, thunderstorm


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
    weather = -50 if day.weather_code in _BAD_CODES else 0.0
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
