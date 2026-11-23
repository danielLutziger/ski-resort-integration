"""Tests for the SLF provider (measured snow depth), with a fake session."""

import asyncio
from datetime import UTC, datetime

import aiohttp
import pytest

from custom_components.ski_resort_recommender.lib.errors import (
    SkiApiConnectionError,
)
from custom_components.ski_resort_recommender.lib.slf import SlfProvider, _depth_at
from tests.fakes import FakeResponse, FakeSession

OPENING = datetime(2026, 11, 23, 8, 0, tzinfo=UTC)  # 09:00 in Zurich
ROWS = [
    {"station_code": "CMA2", "measure_date": "2026-11-23T07:30:00Z", "HS": 60.7},
    {"station_code": "CMA2", "measure_date": "2026-11-23T08:00:00Z", "HS": 61.2},
    {"station_code": "CMA2", "measure_date": "2026-11-23T08:30:00Z", "HS": None},
    {"station_code": "CMA2", "measure_date": "2026-11-23T14:30:00Z", "HS": 73.8},
]


def test_depth_closest_to_the_reference_is_used() -> None:
    """The value at today's opening, not the latest (avoids counting snow twice)."""
    assert _depth_at(ROWS, OPENING) == 61.2


def test_missing_values_are_skipped_and_none_without_any() -> None:
    """HS None is ignored; a station without values gives None."""
    later = datetime(2026, 11, 23, 8, 30, tzinfo=UTC)

    assert _depth_at(ROWS, later) == 61.2  # 08:30 has no HS, 08:00 is closest
    assert (
        _depth_at([{"measure_date": "2026-11-23T08:00:00Z", "HS": None}], later) is None
    )


def test_negative_sensor_values_count_as_no_snow() -> None:
    """The ultrasonic sensor reads a few cm below 0 on bare ground."""
    rows = [{"measure_date": "2026-11-23T08:00:00Z", "HS": -2.1}]

    assert _depth_at(rows, OPENING) == 0


def answer(failing: set[str]) -> FakeSession:
    """Answer every station with ROWS, except the failing ones."""

    def respond(url: str, params: dict) -> FakeResponse:
        assert params == {"period_in_days": 1}
        code = url.rsplit("/", 2)[-2]
        if code in failing:
            return FakeResponse(error=aiohttp.ClientConnectionError("down"))
        return FakeResponse(ROWS if code != "EMPTY" else [])

    return FakeSession(respond)


def test_one_request_per_station_failed_and_empty_stations_left_out() -> None:
    """A failing station does not stop the others."""
    fake = answer(failing={"YBR2"})

    depths = asyncio.run(
        SlfProvider(fake).snow_depths(["CMA2", "YBR2", "EMPTY", "CMA2"], OPENING)
    )

    assert depths == {"CMA2": 61.2}
    assert len(fake.calls) == 3  # duplicates are asked once


def test_every_station_failing_raises() -> None:
    """Only a complete failure is an error (the pipeline keeps the last values)."""
    with pytest.raises(SkiApiConnectionError, match="SLF"):
        asyncio.run(
            SlfProvider(answer(failing={"CMA2", "YBR2"})).snow_depths(
                ["CMA2", "YBR2"], OPENING
            )
        )
