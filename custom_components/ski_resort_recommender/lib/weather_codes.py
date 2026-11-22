"""Classify WMO weather codes (Open-Meteo `weather_code`) for skiing."""

from enum import StrEnum

# TODO: we also need vision scores (how far can you see - more important than weather)


class WeatherClass(StrEnum):
    """How good a weather code is for skiing."""

    VERY_GOOD = "very_good"
    NEUTRAL = "neutral"
    BAD = "bad"
    NO_GO = "no_go"


# codes from https://open-meteo.com/en/docs
_CLASSES: dict[WeatherClass, set[int]] = {
    WeatherClass.VERY_GOOD: {0, 1},  # clear / mainly clear
    WeatherClass.NEUTRAL: {2, 3, 71},  # cloudy, slight snowfall
    WeatherClass.BAD: {
        45,  # fog
        48,  # depositing rime fog
        73,  # moderate snowfall
        75,  # heavy snowfall
        77,  # snow grains
        85,  # slight snow showers
    },
    WeatherClass.NO_GO: {
        51,  # drizzle
        53,  # drizzle
        55,  # drizzle
        56,  # freezing drizzle
        57,  # freezing drizzle
        61,  # rain
        63,  # rain
        65,  # rain
        66,  # freezing rain
        67,  # freezing rain
        80,  # rain showers
        81,  # rain showers
        82,  # rain showers
        86,  # heavy snow showers
        95,  # thunderstorm
        96,  # thunderstorm with slight hail
        97,  # thunderstorm
        99,  # thunderstorm with heavy hail
    },
}

_BY_CODE = {c: cls for cls, codes in _CLASSES.items() for c in codes}


def classify(code: int | None) -> WeatherClass:
    """Return the class of a weather code; unknown or missing codes are neutral."""
    return _BY_CODE.get(code, WeatherClass.NEUTRAL)
