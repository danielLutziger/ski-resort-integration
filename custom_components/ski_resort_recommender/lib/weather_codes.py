"""Classify WMO weather codes (Open-Meteo `weather_code`) for skiing."""

from enum import StrEnum


class WeatherClass(StrEnum):
    """How good a weather code is for skiing."""

    VERY_GOOD = "very_good"
    NEUTRAL = "neutral"
    BAD = "bad"
    NO_GO = "no_go"


# codes from https://open-meteo.com/en/docs
_CLASSES: dict[WeatherClass, set[int]] = {
    WeatherClass.VERY_GOOD: {0, 1},  # clear / mainly clear
    # snowfall is not bad in itself: it counts as fresh snow on the next days and
    # as low visibility on the day itself
    WeatherClass.NEUTRAL: {
        2,  # partly cloudy
        3,  # overcast
        71,  # slight snowfall
        73,  # moderate snowfall
        75,  # heavy snowfall
        77,  # snow grains
        85,  # slight snow showers
        86,  # heavy snow showers
    },
    # fog: visibility covers it for 5 days, the code is the only hint after that
    WeatherClass.BAD: {
        45,  # fog
        48,  # depositing rime fog
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
