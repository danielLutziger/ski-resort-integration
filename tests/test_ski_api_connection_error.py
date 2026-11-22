"""The providers turn network problems into SkiApiConnectionError."""

import asyncio
import json
from datetime import date
from pathlib import Path

import aiohttp
import pytest

from custom_components.ski_resort_recommender.lib.errors import (
    SkiApiConnectionError,
    SkiApiError,
)
from custom_components.ski_resort_recommender.lib.models import Resort, WeatherPoint
from custom_components.ski_resort_recommender.lib.open_meteo import (
    FALLBACK_MODEL,
    OpenMeteoProvider,
)
from custom_components.ski_resort_recommender.lib.sbb import SbbProvider
from custom_components.ski_resort_recommender.lib.settings import Settings
from tests.fakes import FakeResponse, FakeSession

FIXTURES = Path(__file__).parent / "fixtures"
SATURDAY = date(2026, 11, 28)
SETTINGS = Settings(home_station="Zürich HB")


def make_resort(key: str, station: str | None = "Flims Dorf, Bergbahnen") -> Resort:
    """Create a resort with two points (the fixtures hold two locations)."""
    return Resort(
        key=key,
        name=key,
        points=(
            WeatherPoint(name="top", lat=46.8, lon=9.2, elevation_m=2500),
            WeatherPoint(name="mid", lat=46.8, lon=9.2, elevation_m=1800),
        ),
        meteoswiss_point_id=None,
        station=station,
        day_price_chf=None,
    )


def always(response: FakeResponse) -> FakeSession:
    """Create a session that answers every request the same way."""
    return FakeSession(lambda _url, _params: response)


@pytest.mark.parametrize(
    "error",
    [aiohttp.ClientConnectionError("no route"), TimeoutError()],
    ids=["unreachable", "timeout"],
)
def test_open_meteo_network_error_is_a_connection_error(error: BaseException) -> None:
    """Unreachable or too slow: SkiApiConnectionError (a SkiApiError)."""
    provider = OpenMeteoProvider(always(FakeResponse(error=error)))

    with pytest.raises(SkiApiConnectionError):
        asyncio.run(provider.get_forecast([make_resort("a")]))


def test_open_meteo_http_error_is_a_connection_error() -> None:
    """A 5xx answer (e.g. rate limit, server error) is a connection error too."""
    provider = OpenMeteoProvider(always(FakeResponse(status=503)))

    with pytest.raises(SkiApiConnectionError):
        asyncio.run(provider.get_forecast([make_resort("a")]))


def test_open_meteo_both_models_are_requested_and_combined() -> None:
    """Happy path through the fake session: MeteoSwiss + DWD, per point."""
    meteoswiss = json.loads((FIXTURES / "open_meteo_response.json").read_text())
    dwd = json.loads((FIXTURES / "open_meteo_dwd_response.json").read_text())
    session = FakeSession(
        lambda _url, params: FakeResponse(
            dwd if params["models"] == FALLBACK_MODEL else meteoswiss
        )
    )

    forecasts = asyncio.run(OpenMeteoProvider(session).get_forecast([make_resort("a")]))

    assert sorted(call["models"] for call in session.calls) == sorted(
        ["meteoswiss_icon_seamless", FALLBACK_MODEL]
    )
    assert all(call["elevation"] == "2500,1800" for call in session.calls)
    assert list(forecasts["a"]) == ["top", "mid"]


def test_sbb_network_error_is_a_connection_error() -> None:
    """One connection request that fails raises SkiApiConnectionError."""
    provider = SbbProvider(always(FakeResponse(error=aiohttp.ClientConnectionError())))

    with pytest.raises(SkiApiConnectionError):
        asyncio.run(provider.connection("Flims Dorf, Bergbahnen", SATURDAY, SETTINGS))


def test_sbb_one_failing_resort_does_not_break_the_others() -> None:
    """connections(): the failing resort is left out, the others are returned."""
    payload = json.loads((FIXTURES / "sbb_connections.json").read_text())
    session = FakeSession(
        lambda _url, params: (
            FakeResponse(status=500)
            if params["to"] == "Broken"
            else FakeResponse(payload)
        )
    )
    resorts = [make_resort("ok"), make_resort("broken", station="Broken")]

    found = asyncio.run(SbbProvider(session).connections(resorts, SATURDAY, SETTINGS))

    assert list(found) == ["ok"]


def test_sbb_without_home_station_makes_no_request() -> None:
    """No home station configured: no connections, no network calls."""
    session = always(FakeResponse(error=AssertionError("must not be called")))

    found = asyncio.run(
        SbbProvider(session).connections(
            [make_resort("a")], SATURDAY, Settings(home_station=None)
        )
    )

    assert found == {}
    assert session.calls == []


def test_sbb_unexpected_errors_are_not_swallowed() -> None:
    """Only SkiApiError is skipped per resort; real bugs still surface."""
    session = always(FakeResponse(error=RuntimeError("bug")))

    with pytest.raises(RuntimeError):
        asyncio.run(
            SbbProvider(session).connections([make_resort("a")], SATURDAY, SETTINGS)
        )


def test_all_provider_errors_share_one_base_class() -> None:
    """The coordinator only needs to catch SkiApiError."""
    assert issubclass(SkiApiConnectionError, SkiApiError)


def error_message(provider_call: object) -> str:
    """Run the call and return the SkiApiConnectionError message."""
    with pytest.raises(SkiApiConnectionError) as error:
        asyncio.run(provider_call)  # type: ignore[arg-type]
    return str(error.value)


def test_rate_limit_message_is_short_and_clear() -> None:
    """429 says "rate limit" and does not dump the 100-coordinate URL."""
    provider = OpenMeteoProvider(always(FakeResponse(status=429)))

    message = error_message(provider.get_forecast([make_resort("a")]))

    assert message == "Open-Meteo rate limit (HTTP 429 Too Many Requests)"


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (FakeResponse(status=503), "Open-Meteo HTTP 503 Service Unavailable"),
        (FakeResponse(error=TimeoutError()), "Open-Meteo timeout"),
        (
            FakeResponse(error=aiohttp.ClientConnectionError("no route")),
            "Open-Meteo unreachable (ClientConnectionError)",
        ),
    ],
    ids=["http", "timeout", "unreachable"],
)
def test_open_meteo_error_messages(response: FakeResponse, message: str) -> None:
    """Each kind of problem has a readable message for the sensor and the log."""
    provider = OpenMeteoProvider(always(response))

    assert error_message(provider.get_forecast([make_resort("a")])) == message


def test_sbb_error_message_names_the_source() -> None:
    """SBB problems say SBB (they only cost the train connection)."""
    provider = SbbProvider(always(FakeResponse(status=503)))

    message = error_message(
        provider.connection("Flims Dorf, Bergbahnen", SATURDAY, SETTINGS)
    )

    assert message == "SBB HTTP 503 Service Unavailable"
