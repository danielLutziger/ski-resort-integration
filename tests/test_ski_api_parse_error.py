"""The providers turn unexpected answers into SkiApiParseError."""

import asyncio
import json
from datetime import date
from pathlib import Path

import pytest

from custom_components.ski_resort_recommender.lib.errors import (
    SkiApiError,
    SkiApiParseError,
)
from custom_components.ski_resort_recommender.lib.models import Resort, WeatherPoint
from custom_components.ski_resort_recommender.lib.open_meteo import OpenMeteoProvider
from custom_components.ski_resort_recommender.lib.sbb import SbbProvider
from custom_components.ski_resort_recommender.lib.settings import Settings
from tests.fakes import FakeResponse, FakeSession

FIXTURES = Path(__file__).parent / "fixtures"
SATURDAY = date(2026, 11, 28)
SETTINGS = Settings(home_station="Zürich HB")


def make_resort(points: int) -> Resort:
    """Create a resort with the given number of points."""
    return Resort(
        key="a",
        name="a",
        points=tuple(
            WeatherPoint(name=f"p{i}", lat=46.8, lon=9.2, elevation_m=2000)
            for i in range(points)
        ),
        meteoswiss_point_id=None,
        station="Flims Dorf, Bergbahnen",
        day_price_chf=None,
    )


def answer(payload: object) -> FakeSession:
    """Create a session that answers every request with payload."""
    return FakeSession(lambda _url, _params: FakeResponse(payload))


def test_open_meteo_wrong_location_count_is_a_parse_error() -> None:
    """Three points requested, two locations answered: positions can't be matched."""
    two_locations = json.loads((FIXTURES / "open_meteo_response.json").read_text())

    with pytest.raises(SkiApiParseError):
        asyncio.run(
            OpenMeteoProvider(answer(two_locations)).get_forecast([make_resort(3)])
        )


def test_open_meteo_missing_block_is_a_parse_error() -> None:
    """An answer without the daily/hourly blocks raises SkiApiParseError."""
    with pytest.raises(SkiApiParseError):
        asyncio.run(
            OpenMeteoProvider(answer([{"latitude": 46.8}])).get_forecast(
                [make_resort(1)]
            )
        )


def test_open_meteo_error_object_is_a_parse_error() -> None:
    """Open-Meteo's error body ({"error": true, "reason": ...}) is not a forecast."""
    body = {"error": True, "reason": "Parameter 'models' is invalid"}

    with pytest.raises(SkiApiParseError):
        asyncio.run(OpenMeteoProvider(answer(body)).get_forecast([make_resort(1)]))


def test_sbb_answer_without_connections_is_a_parse_error() -> None:
    """An SBB answer without "connections" raises SkiApiParseError."""
    with pytest.raises(SkiApiParseError):
        asyncio.run(
            SbbProvider(answer({"errors": [{"message": "boom"}]})).connection(
                "Flims Dorf, Bergbahnen", SATURDAY, SETTINGS
            )
        )


def test_sbb_bad_time_stamp_is_a_parse_error() -> None:
    """A connection with an unreadable time stamp raises SkiApiParseError."""
    payload = json.loads((FIXTURES / "sbb_connections.json").read_text())
    payload["connections"][0]["from"]["departure"] = "tomorrow morning"

    with pytest.raises(SkiApiParseError):
        asyncio.run(
            SbbProvider(answer(payload)).connection(
                "Flims Dorf, Bergbahnen", SATURDAY, SETTINGS
            )
        )


def test_parse_errors_are_ski_api_errors() -> None:
    """The coordinator only needs to catch SkiApiError."""
    assert issubclass(SkiApiParseError, SkiApiError)
