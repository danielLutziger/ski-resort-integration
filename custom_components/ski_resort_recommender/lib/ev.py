"""Public EV charging points from the Swiss Federal Office of Energy (BFE)."""

import math
from dataclasses import replace
from typing import TYPE_CHECKING

import aiohttp

from custom_components.ski_resort_recommender.lib.errors import (
    SkiApiConnectionError,
    SkiApiParseError,
    describe,
)
from custom_components.ski_resort_recommender.lib.models import (
    AccessPoint,
    Charger,
    Drive,
    Resort,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

# every charging point in Switzerland, updated daily (~1 MB, gzip); open use with
# a source reference, commercial use only with permission
URL = (
    "https://data.geo.admin.ch/ch.bfe.ladestellen-elektromobilitaet/data/"
    "ch.bfe.ladestellen-elektromobilitaet.json"
)
ATTRIBUTION = "Swiss Federal Office of Energy SFOE (ich-tanke-strom.ch)"
PUBLIC = {"Free publicly accessible", "Paying publicly accessible"}
NEAR_M = 300  # a charger this close to the access point or a car park counts
COVERAGE_M = 3000  # no charger at all within this: no data there (e.g. Austria)


class BfeProvider:
    """Fetch the public charging points (one request, once a day)."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        """Use the injected aiohttp session (HA: async_get_clientsession)."""
        self._session = session

    async def chargers(self, resorts: Sequence[Resort]) -> list[Charger]:
        """Return the chargers near the resorts' access points."""
        try:
            async with self._session.get(
                URL, params={}, timeout=aiohttp.ClientTimeout(total=60)
            ) as response:
                response.raise_for_status()
                payload = await response.json()  # aiohttp unpacks the gzip
        except (aiohttp.ClientError, TimeoutError) as error:
            raise SkiApiConnectionError(describe("BFE", error)) from error
        try:
            chargers = _parse(payload)
        except (KeyError, IndexError, TypeError, ValueError) as error:
            msg = f"BFE: {error}"
            raise SkiApiParseError(msg) from error
        places = [(a.lat, a.lon) for r in resorts for a in r.access]
        return [c for c in chargers if _within(c, places, COVERAGE_M)]


def _parse(payload: dict) -> list[Charger]:
    """Charging points (OICP EVSE records) with their highest power."""
    chargers = []
    for operator in payload["EVSEData"]:
        for record in operator["EVSEDataRecord"]:
            lat, lon = record["GeoCoordinates"]["Google"].replace(",", " ").split()
            powers = [
                float(f.get("power") or 0)
                for f in record.get("ChargingFacilities") or []
            ]
            chargers.append(
                Charger(
                    float(lat),
                    float(lon),
                    max(powers, default=0),
                    public=record.get("Accessibility") in PUBLIC,
                )
            )
    return chargers


def attach_chargers(
    resorts: Sequence[Resort], drives: dict[str, Drive], chargers: list[Charger]
) -> dict[str, Drive]:
    """Add the power of every charger near the chosen access point to the drive."""
    access = {
        (r.key, a.name): a for r in resorts for a in r.access
    }  # the drive names its access point
    result = {}
    for key, drive in drives.items():
        point = access.get((key, drive.access))
        result[key] = (
            replace(drive, chargers_kw=_near(point, chargers)) if point else drive
        )
    return result


def _near(point: AccessPoint, chargers: list[Charger]) -> tuple[float, ...] | None:
    """
    Power of the public chargers at the access point; None without data around.

    Any charger within COVERAGE_M (also a restricted one) shows that the data
    covers the place; only public chargers within NEAR_M are counted.
    """
    if not any(_within(c, [(point.lat, point.lon)], COVERAGE_M) for c in chargers):
        return None
    places = [(point.lat, point.lon), *((p.lat, p.lon) for p in point.parking)]
    return tuple(
        sorted(
            (c.power_kw for c in chargers if c.public and _within(c, places, NEAR_M)),
            reverse=True,
        )
    )


def _within(c: Charger, places: Iterable[tuple[float, float]], metres: float) -> bool:
    """Return True if the charger is within the distance of one of the places."""
    degrees = metres / 111_000  # quick check first: 1 degree latitude ~ 111 km
    for lat, lon in places:
        if abs(c.lat - lat) > degrees or abs(c.lon - lon) > 2 * degrees:
            continue
        dy = math.radians(c.lat - lat)
        dx = math.radians(c.lon - lon) * math.cos(math.radians(lat))
        if 6_371_000 * math.hypot(dx, dy) <= metres:
            return True
    return False
