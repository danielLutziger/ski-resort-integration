"""Tests for build_recommendations(): forecasts + SBB + ranking, with fakes."""

import asyncio
import json
from dataclasses import replace
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from custom_components.ski_resort_recommender.lib.errors import SkiApiConnectionError
from custom_components.ski_resort_recommender.lib.models import Resort, WeatherPoint
from custom_components.ski_resort_recommender.lib.open_meteo import (
    FALLBACK_MODEL,
)
from custom_components.ski_resort_recommender.lib.open_meteo import (
    URL as OPEN_METEO_URL,
)
from custom_components.ski_resort_recommender.lib.pipeline import (
    Cache,
    build_recommendations,
)
from custom_components.ski_resort_recommender.lib.settings import Settings
from tests.fakes import FakeResponse, FakeSession

FIXTURES = Path(__file__).parent / "fixtures"
MS = json.loads((FIXTURES / "open_meteo_response.json").read_text())
DWD = json.loads((FIXTURES / "open_meteo_dwd_response.json").read_text())
SBB = (FIXTURES / "sbb_connections.json").read_text()  # Sat 28.11
TODAY = date(2026, 11, 21)  # the fixtures hold 20.-24.11
NOW = datetime(2026, 11, 21, 10, 0, tzinfo=ZoneInfo("Europe/Zurich"))
SETTINGS = Settings(
    allowed_weekdays=frozenset(range(7)),
    max_results=3,
    min_good_score=60,
    home_station="Zürich HB",
    weather_interval=timedelta(hours=3),
    weather_max_age=timedelta(hours=12),
)


def make_resort(key: str) -> Resort:
    """Create a resort with two points (the weather fixtures hold two locations)."""
    return Resort(
        key=key,
        name=key,
        points=(
            WeatherPoint(name="top", lat=46.8, lon=9.2, elevation_m=2500),
            WeatherPoint(name="mid", lat=46.8, lon=9.2, elevation_m=1800),
        ),
        meteoswiss_point_id=None,
        station="Flims Dorf, Bergbahnen",
        day_price_chf=90,
    )


def sbb_payload(day: date) -> dict:
    """Return the saved SBB answer, moved to the given day."""
    return json.loads(SBB.replace("2026-11-28", day.isoformat()))


def session(*, weather_error: BaseException | None = None) -> FakeSession:
    """Answer Open-Meteo with the fixtures and SBB with the saved connections."""

    def respond(url: str, params: dict) -> FakeResponse:
        if url == OPEN_METEO_URL:
            if weather_error:
                return FakeResponse(error=weather_error)
            return FakeResponse(DWD if params["models"] == FALLBACK_MODEL else MS)
        return FakeResponse(sbb_payload(date.fromisoformat(params["date"])))

    return FakeSession(respond)


def sbb_calls(fake: FakeSession) -> list[dict]:
    """Only the SBB requests of a session."""
    return [c for c in fake.calls if "from" in c]


def test_recommendations_get_travel_points_and_the_connection_of_their_day() -> None:
    """Ranking with travel/price, and the shown results carry their train."""
    fake = session()

    result = asyncio.run(
        build_recommendations(
            fake, [make_resort("laax")], SETTINGS, now=NOW, cache=Cache()
        )
    )

    assert result.recommendations
    for r in result.recommendations:
        assert r.score.reasons["travel"] == 5  # only resort: shortest trip
        assert r.connection is not None
        assert r.connection.departure.date() == r.day.day


def test_travel_times_are_fetched_once_per_day() -> None:
    """A second update on the same day reuses the cached travel times."""
    fake = session()
    cache = Cache()
    resorts = [make_resort("laax")]
    only_travel = replace(SETTINGS, max_results=0)  # no exact connections

    asyncio.run(build_recommendations(fake, resorts, only_travel, now=NOW, cache=cache))
    first = len(sbb_calls(fake))
    asyncio.run(build_recommendations(fake, resorts, only_travel, now=NOW, cache=cache))
    again = len(sbb_calls(fake)) - first
    asyncio.run(
        build_recommendations(
            fake, resorts, only_travel, now=NOW + timedelta(days=1), cache=cache
        )
    )
    next_day = len(sbb_calls(fake)) - first - again

    assert (first, again, next_day) == (1, 0, 1)


def test_without_home_station_there_are_no_sbb_requests() -> None:
    """No home station: no travel score, no connections, no SBB calls."""
    fake = session()

    result = asyncio.run(
        build_recommendations(
            fake,
            [make_resort("laax")],
            replace(SETTINGS, home_station=None),
            now=NOW,
            cache=Cache(),
        )
    )

    assert sbb_calls(fake) == []
    assert all(r.connection is None for r in result.recommendations)


def test_weather_errors_reach_the_caller() -> None:
    """Without forecasts there is nothing to rank: SkiApiError goes up."""
    fake = session(weather_error=TimeoutError())

    with pytest.raises(SkiApiConnectionError):
        asyncio.run(
            build_recommendations(
                fake, [make_resort("laax")], SETTINGS, now=NOW, cache=Cache()
            )
        )


def test_a_failing_exact_connection_keeps_the_reference_connection() -> None:
    """SBB down for one exact request: the recommendation keeps the reference."""
    calls = {"n": 0}

    def respond(url: str, params: dict) -> FakeResponse:
        if url == OPEN_METEO_URL:
            return FakeResponse(DWD if params["models"] == FALLBACK_MODEL else MS)
        calls["n"] += 1
        if calls["n"] > 1:  # the reference request works, the exact ones fail
            return FakeResponse(status=503)
        return FakeResponse(sbb_payload(date.fromisoformat(params["date"])))

    result = asyncio.run(
        build_recommendations(
            FakeSession(respond),
            [make_resort("laax")],
            SETTINGS,
            now=NOW,
            cache=Cache(),
        )
    )

    assert result.recommendations
    assert all(r.connection is not None for r in result.recommendations)


def update(
    fake: FakeSession,
    resorts: list[Resort],
    settings: Settings,
    now: datetime,
    cache: Cache,
) -> None:
    """Run one update (result not needed)."""
    asyncio.run(build_recommendations(fake, resorts, settings, now=now, cache=cache))


def weather_calls(fake: FakeSession) -> int:
    """Count the Open-Meteo requests (two per forecast: MeteoSwiss + DWD)."""
    return sum("models" in c for c in fake.calls)


def test_forecasts_are_reused_within_the_weather_interval() -> None:
    """Hourly updates, weather only every weather_interval (Open-Meteo budget)."""
    fake = session()
    cache = Cache()
    resorts = [make_resort("laax")]
    no_train = replace(SETTINGS, home_station=None)

    for hours in (0, 1, 2):  # within 3 h: one forecast
        update(fake, resorts, no_train, NOW + timedelta(hours=hours), cache)
    within = weather_calls(fake)
    update(fake, resorts, no_train, NOW + timedelta(hours=3), cache)

    assert (within, weather_calls(fake)) == (2, 4)


def test_rate_limited_weather_keeps_the_last_forecast_for_a_while() -> None:
    """429 after a good update: the last forecast is used up to weather_max_age."""
    cache = Cache()
    resorts = [make_resort("laax")]
    no_train = replace(SETTINGS, home_station=None)
    asyncio.run(
        build_recommendations(session(), resorts, no_train, now=NOW, cache=cache)
    )
    limited = FakeSession(lambda _url, _params: FakeResponse(status=429))

    later = asyncio.run(
        build_recommendations(
            limited, resorts, no_train, now=NOW + timedelta(hours=5), cache=cache
        )
    )

    assert later.recommendations  # ranked from the cached forecast
    with pytest.raises(SkiApiConnectionError):  # too old after 12 h
        asyncio.run(
            build_recommendations(
                limited, resorts, no_train, now=NOW + timedelta(hours=13), cache=cache
            )
        )


def test_all_results_survive_the_exact_connections() -> None:
    """With a home station the modal still gets every resort-day."""
    result = asyncio.run(
        build_recommendations(
            session(), [make_resort("laax")], SETTINGS, now=NOW, cache=Cache()
        )
    )

    assert result.all
    assert len(result.all) >= len(result.recommendations)
