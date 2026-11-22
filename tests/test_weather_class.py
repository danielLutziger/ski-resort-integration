"""Tests for the weather code classification."""

import pytest

from custom_components.ski_resort_recommender.lib.weather_codes import (
    _CLASSES,
    WeatherClass,
    WeatherIcon,
    classify,
    weather_icon,
)

ALL_CODES = {
    0,
    1,
    2,
    3,
    45,
    48,
    51,
    53,
    55,
    56,
    57,
    61,
    63,
    65,
    66,
    67,
    71,
    73,
    75,
    77,
    80,
    81,
    82,
    85,
    86,
    95,
    96,
    97,
    99,
}


def test_every_documented_code_is_classified_exactly_once() -> None:
    """Every documented WMO code is in exactly one class."""
    assigned = [c for codes in _CLASSES.values() for c in codes]
    assert len(assigned) == len(set(assigned))
    assert set(assigned) == ALL_CODES


def test_unknown_is_neutral() -> None:
    """A missing code is neutral."""
    assert classify(None) == WeatherClass.NEUTRAL


def test_weather_icon_takes_the_most_frequent_kind_of_weather() -> None:
    """Six sunny hours and two cloudy ones: sunny."""
    icon = weather_icon([(1, (0, 0, 1, 1, 0, 0, 3, 3))])

    assert icon is WeatherIcon.SUNNY
    assert icon.mdi == "mdi:weather-sunny"


def test_weather_icon_weights_the_points() -> None:
    """A heavy main area outweighs a cloudy side area."""
    main = (2, (2, 2, 2, 2))  # partly cloudy, weight 2
    side = (1, (3, 3, 3, 3, 3))  # cloudy, weight 1

    assert weather_icon([main, side]) is WeatherIcon.PARTLY_CLOUDY


def test_weather_icon_tie_goes_to_the_worse_weather() -> None:
    """Four sunny and four snowy hours: snow."""
    assert weather_icon([(1, (0, 0, 0, 0, 75, 75, 73, 71))]) is WeatherIcon.SNOW


def test_weather_icon_covers_every_classified_code() -> None:
    """Every documented WMO code has an icon."""
    for codes in _CLASSES.values():
        for code in codes:
            assert isinstance(weather_icon([(1, (code,))]), WeatherIcon)


def test_weather_icon_without_codes_is_unknown() -> None:
    """No data at all: a neutral icon."""
    assert weather_icon([(1, ())]) is WeatherIcon.UNKNOWN


@pytest.mark.parametrize(
    ("sun_share", "icon"),
    [
        (0.9, WeatherIcon.SUNNY),
        (0.6, WeatherIcon.SUNNY),
        (0.4, WeatherIcon.PARTLY_CLOUDY),
        (0.1, WeatherIcon.CLOUDY),
        (None, WeatherIcon.CLOUDY),
    ],
)
def test_dry_weather_icon_follows_the_sunshine(
    sun_share: float | None, icon: WeatherIcon
) -> None:
    """'Overcast' codes with lots of measured sun (thin high cloud) look sunny."""
    overcast = [(1, (3, 3, 3, 3, 3, 3, 3, 3))]

    assert weather_icon(overcast, sun_share=sun_share) is icon


def test_snow_and_rain_icons_ignore_the_sunshine() -> None:
    """Precipitation stays visible, even with some sun in between."""
    assert weather_icon([(1, (73, 73, 73))], sun_share=0.7) is WeatherIcon.SNOW
    assert weather_icon([(1, (63, 63, 63))], sun_share=0.7) is WeatherIcon.RAIN
