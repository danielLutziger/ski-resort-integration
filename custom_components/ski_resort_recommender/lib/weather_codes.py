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


class WeatherIcon(StrEnum):
    """Weather symbol of a resort-day; the value is the Home Assistant mdi icon."""

    SUNNY = "mdi:weather-sunny"
    PARTLY_CLOUDY = "mdi:weather-partly-cloudy"
    CLOUDY = "mdi:weather-cloudy"
    FOG = "mdi:weather-fog"
    SNOW = "mdi:weather-snowy"
    RAIN = "mdi:weather-rainy"
    THUNDER = "mdi:weather-lightning"
    UNKNOWN = "mdi:weather-cloudy-alert"

    @property
    def mdi(self) -> str:
        """Home Assistant icon name."""
        return self.value

    @property
    def emoji(self) -> str:
        """Symbol for the Markdown table."""
        return _EMOJI[self]


_EMOJI = {
    WeatherIcon.SUNNY: "☀️",
    WeatherIcon.PARTLY_CLOUDY: "⛅",
    WeatherIcon.CLOUDY: "☁️",
    WeatherIcon.FOG: "🌫️",
    WeatherIcon.SNOW: "🌨️",
    WeatherIcon.RAIN: "🌧️",
    WeatherIcon.THUNDER: "⛈️",
    WeatherIcon.UNKNOWN: "❔",
}
# WMO code -> icon; the order of _SEVERITY breaks ties (worse weather wins)
_ICON_CODES = {
    WeatherIcon.SUNNY: {0, 1},
    WeatherIcon.PARTLY_CLOUDY: {2},
    WeatherIcon.CLOUDY: {3},
    WeatherIcon.FOG: {45, 48},
    WeatherIcon.SNOW: {71, 73, 75, 77, 85, 86},
    WeatherIcon.RAIN: {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82},
    WeatherIcon.THUNDER: {95, 96, 97, 99},
}
_ICON_BY_CODE = {c: icon for icon, codes in _ICON_CODES.items() for c in codes}
_SEVERITY = list(_ICON_CODES)


_DRY = (WeatherIcon.SUNNY, WeatherIcon.PARTLY_CLOUDY, WeatherIcon.CLOUDY)
SUNNY_FROM_SHARE = 0.6  # sunshine / daylight from which a dry day looks sunny
PARTLY_FROM_SHARE = 0.25


def weather_icon(
    weighted_codes: list[tuple[float, tuple[int, ...]]],
    *,
    sun_share: float | None = None,
) -> WeatherIcon:
    """
    Return the most frequent weather over all ski hours of all points (weighted).

    For dry weather the measured sunshine share decides between sunny, partly
    cloudy and cloudy: the models often report "overcast" for thin high cloud.
    """
    icon = _most_frequent(weighted_codes)
    if icon not in _DRY or sun_share is None:
        return icon
    if sun_share >= SUNNY_FROM_SHARE:
        return WeatherIcon.SUNNY
    if sun_share >= PARTLY_FROM_SHARE:
        return WeatherIcon.PARTLY_CLOUDY
    return WeatherIcon.CLOUDY


def _most_frequent(weighted_codes: list[tuple[float, tuple[int, ...]]]) -> WeatherIcon:
    """Icon with the most (weighted) ski hours; ties go to the worse weather."""
    votes: dict[WeatherIcon, float] = {}
    for weight, codes in weighted_codes:
        for code in codes:
            icon = _ICON_BY_CODE.get(code)
            if icon:
                votes[icon] = votes.get(icon, 0) + weight
    if not votes:
        return WeatherIcon.UNKNOWN
    return max(votes, key=lambda icon: (votes[icon], _SEVERITY.index(icon)))
