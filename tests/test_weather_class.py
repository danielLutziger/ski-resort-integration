"""Tests for the weather code classification."""

from custom_components.ski_resort_recommender.lib.weather_codes import (
    _CLASSES,
    WeatherClass,
    classify,
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
