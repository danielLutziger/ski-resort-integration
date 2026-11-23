"""Tests for the BFE charging points and their matching to the access points."""

import asyncio

import aiohttp
import pytest

from custom_components.ski_resort_recommender.lib.errors import SkiApiConnectionError
from custom_components.ski_resort_recommender.lib.ev import (
    BfeProvider,
    _parse,
    attach_chargers,
)
from custom_components.ski_resort_recommender.lib.models import (
    AccessPoint,
    CarPark,
    Charger,
    Drive,
    Resort,
    WeatherPoint,
)
from tests.fakes import FakeResponse, FakeSession

STENNA = CarPark(name="Stenna", lat=46.8330, lon=9.2818)
FLIMS = AccessPoint(name="Flims", lat=46.8345, lon=9.2823, parking=(STENNA,))
DRIVE = Drive(access="Flims", duration_min=101, distance_km=138.5)


def make_resort(*access: AccessPoint) -> Resort:
    """Create the test resort with the given access points."""
    return Resort(
        key="laax",
        name="Flims Laax",
        points=(WeatherPoint(name="top", lat=46.8, lon=9.2, elevation_m=2200),),
        meteoswiss_point_id=None,
        station="",
        day_price_chf=None,
        access=access,
    )


def record(lat: float, lon: float, access: str, *powers: object) -> dict:
    """One OICP EVSE record as the BFE file has it."""
    return {
        "Accessibility": access,
        "GeoCoordinates": {"Google": f"{lat} {lon}"},
        "ChargingFacilities": [{"power": p} for p in powers],
    }


PAYLOAD = {
    "EVSEData": [
        {
            "EVSEDataRecord": [
                record(46.8333, 9.2820, "Free publicly accessible", "22.0"),
                record(46.8336, 9.2821, "Paying publicly accessible", 11, 50),
                record(46.8334, 9.2822, "Restricted access", "22.0"),  # hotel guests
                record(46.8400, 9.3000, "Free publicly accessible", 22),  # 1.5 km
                record(47.3779, 8.5402, "Free publicly accessible", 22),  # Zürich
            ]
        }
    ]
}


def test_chargers_with_their_highest_power_and_access() -> None:
    """Power comes as text or number; restricted chargers are marked."""
    chargers = _parse(PAYLOAD)

    assert len(chargers) == 5
    assert chargers[0] == Charger(46.8333, 9.2820, 22.0)
    assert chargers[1].power_kw == 50
    assert [c.public for c in chargers] == [True, True, False, True, True]


def test_provider_keeps_only_chargers_around_the_resorts() -> None:
    """One request; chargers far from every access point are dropped."""
    session = FakeSession(lambda *_: FakeResponse(PAYLOAD))

    chargers = asyncio.run(BfeProvider(session).chargers([make_resort(FLIMS)]))

    assert len(session.calls) == 1
    assert len(chargers) == 4  # Zürich is not near a resort


def test_provider_errors_are_ski_api_errors() -> None:
    """A failed download is a connection error (the pipeline keeps the last)."""
    session = FakeSession(
        lambda *_: FakeResponse(error=aiohttp.ClientConnectionError("down"))
    )

    with pytest.raises(SkiApiConnectionError, match="BFE"):
        asyncio.run(BfeProvider(session).chargers([make_resort(FLIMS)]))


def test_chargers_near_the_access_point_or_its_car_parks_count() -> None:
    """Within 300 m: counted, fastest first; 1.5 km away: not counted."""
    drives = attach_chargers([make_resort(FLIMS)], {"laax": DRIVE}, _parse(PAYLOAD))

    assert drives["laax"].chargers_kw == (50.0, 22.0)


def test_only_restricted_chargers_around_is_zero_not_none() -> None:
    """The data covers the place, but nothing is public: 0 chargers."""
    hotel = [Charger(46.8334, 9.2822, 22, public=False)]

    drives = attach_chargers([make_resort(FLIMS)], {"laax": DRIVE}, hotel)

    assert drives["laax"].chargers_kw == ()


def test_no_charger_data_around_is_none_not_zero() -> None:
    """Nothing within 3 km (e.g. Austria): unknown, not 0 chargers."""
    far = [Charger(47.3779, 8.5402, 22)]

    drives = attach_chargers([make_resort(FLIMS)], {"laax": DRIVE}, far)

    assert drives["laax"].chargers_kw is None
