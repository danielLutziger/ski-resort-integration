"""Tests for the OSRM provider (drive times), with a fake session."""

import asyncio

import aiohttp
import pytest

from custom_components.ski_resort_recommender.lib.errors import (
    SkiApiConnectionError,
    SkiApiParseError,
)
from custom_components.ski_resort_recommender.lib.models import (
    AccessPoint,
    CarPark,
    Drive,
    Resort,
    WeatherPoint,
)
from custom_components.ski_resort_recommender.lib.osrm import OsrmProvider
from tests.fakes import FakeResponse, FakeSession

ZURICH_HB = (47.3779, 8.5402)
FLIMS = AccessPoint(name="Flims", lat=46.8345, lon=9.2823)
LAAX = AccessPoint(name="Laax", lat=46.8202, lon=9.2633)
TANNENBODEN = AccessPoint(name="Tannenboden", lat=47.0925, lon=9.2804)


def make_resort(key: str, *access: AccessPoint) -> Resort:
    """Create a resort with the given access points."""
    return Resort(
        key=key,
        name=key,
        points=(WeatherPoint(name="top", lat=46.8, lon=9.2, elevation_m=2200),),
        meteoswiss_point_id=None,
        station="",
        day_price_chf=None,
        access=access,
    )


def table(durations: list, distances: list) -> dict:
    """OSRM /table answer: row 0 from home (column 0 = home itself)."""
    return {
        "code": "Ok",
        "durations": [[0, *durations]],
        "distances": [[0, *distances]],
    }


def run(payload: dict | None = None, *, error: BaseException | None = None) -> tuple:
    """Ask for Flims Laax (2 access points) and Flumserberg; return result + calls."""
    urls: list[str] = []

    def respond(url: str, params: dict) -> FakeResponse:
        urls.append(url)
        assert params == {"sources": "0", "annotations": "duration,distance"}
        return FakeResponse(error=error) if error else FakeResponse(payload)

    resorts = [
        make_resort("laax", FLIMS, LAAX),
        make_resort("flumserberg", TANNENBODEN),
    ]
    drives = asyncio.run(OsrmProvider(FakeSession(respond)).drives(ZURICH_HB, resorts))
    return drives, urls


def test_one_request_with_home_first_and_lon_lat_order() -> None:
    """All access points in one request; OSRM wants lon,lat."""
    _, urls = run(table([6060, 6120, 3600], [138500, 141800, 80200]))

    assert urls == [
        "https://router.project-osrm.org/table/v1/driving/"
        "8.5402,47.3779;9.2823,46.8345;9.2633,46.8202;9.2804,47.0925"
    ]


def test_the_closest_access_point_wins_per_resort() -> None:
    """Flims 101 min beats Laax 102 min; minutes and km are rounded."""
    drives, _ = run(table([6060, 6120, 3600], [138500, 141800, 80240]))

    assert drives == {
        "laax": Drive(access="Flims", duration_min=101, distance_km=138.5),
        "flumserberg": Drive(access="Tannenboden", duration_min=60, distance_km=80.2),
    }


def test_unreachable_access_points_are_skipped() -> None:
    """OSRM returns null for a point it cannot reach."""
    drives, _ = run(table([None, 6120, None], [None, 141800, None]))

    assert drives == {"laax": Drive(access="Laax", duration_min=102, distance_km=141.8)}


def test_resorts_without_access_points_need_no_request() -> None:
    """No access points: no request at all."""
    session = FakeSession(lambda *_: pytest.fail("no request expected"))

    drives = asyncio.run(OsrmProvider(session).drives(ZURICH_HB, [make_resort("a")]))

    assert drives == {}


def test_errors_become_ski_api_errors() -> None:
    """Connection problems and an OSRM error answer have their own types."""
    with pytest.raises(SkiApiConnectionError, match="OSRM"):
        run(error=aiohttp.ClientConnectionError("down"))
    with pytest.raises(SkiApiParseError, match="Too many"):
        run({"code": "TooBig", "message": "Too many table coordinates"})


def test_the_drive_carries_the_car_parks_of_its_access_point() -> None:
    """The card shows the car parks of the chosen access point."""
    stenna = CarPark(name="Stenna", lat=46.833, lon=9.282, spaces=1147, price_chf=13.6)
    flims = AccessPoint(name="Flims", lat=46.8345, lon=9.2823, parking=(stenna,))
    session = FakeSession(lambda *_: FakeResponse(table([6060], [138500])))

    drives = asyncio.run(
        OsrmProvider(session).drives(ZURICH_HB, [make_resort("laax", flims)])
    )

    assert drives["laax"].parking == (stenna,)


def test_route_is_the_road_as_lat_lon_points() -> None:
    """One request per route; OSRM sends lon, lat."""
    answer = {
        "code": "Ok",
        "routes": [{"geometry": {"coordinates": [[8.54, 47.378], [9.28, 46.83]]}}],
    }
    calls: list[tuple] = []

    def respond(url: str, params: dict) -> FakeResponse:
        calls.append((url, params))
        return FakeResponse(answer)

    route = asyncio.run(OsrmProvider(FakeSession(respond)).route(ZURICH_HB, FLIMS))

    assert route == ((47.378, 8.54), (46.83, 9.28))
    assert calls == [
        (
            "https://router.project-osrm.org/route/v1/driving/8.5402,47.3779;9.2823,46.8345",
            {"overview": "simplified", "geometries": "geojson"},
        )
    ]
