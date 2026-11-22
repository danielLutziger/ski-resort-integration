from enum import StrEnum


class WeatherClass(StrEnum):
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
        48,  # moderate / heavy snow
        73,  # snow grains
        75,  # snow grains
        77,  # snow grains
        85,  # slight snow showers
    },
    WeatherClass.NO_GO: {
        51,  # drizzle
        53,  # drizzle
        55,  # drizzle
        56,  # drizzle
        57,  # drizzle
        61,  # rain
        63,  # rain
        65,  # rain
        66,  # rain
        67,  # rain
        80,  # rain showers
        81,  # rain showers
        82,  # rain showers
        86,  # heavy snow showers
        95,  # thunderstorm
        96,  # thunderstorm
        97,  # thunderstorm
        99,  # thunderstorm
    },
}

_BY_CODE = {c: cls for cls, codes in _CLASSES.items() for c in codes}


def classify(code: int | None) -> WeatherClass:
    return _BY_CODE.get(code, WeatherClass.NEUTRAL)  # if unknown class return neutral
