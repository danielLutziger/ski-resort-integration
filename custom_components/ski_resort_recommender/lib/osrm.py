"""Drive times by car from the public OSRM server (OpenStreetMap data)."""

from typing import TYPE_CHECKING

import aiohttp

from custom_components.ski_resort_recommender.lib.errors import (
    SkiApiConnectionError,
    SkiApiParseError,
    describe,
)
from custom_components.ski_resort_recommender.lib.models import (
    AccessPoint,
    Drive,
    Resort,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

# demo server: free, no key, best effort, no traffic; one request a day is fine
URL = "https://router.project-osrm.org/table/v1/driving/{coordinates}"
# the data licence (ODbL) asks for this reference
ATTRIBUTION = "OSRM, map data © OpenStreetMap contributors"


class OsrmProvider:
    """Fetch the drive time from home to every access point in one request."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        """Use the injected aiohttp session (HA: async_get_clientsession)."""
        self._session = session

    async def drives(
        self, origin: tuple[float, float], resorts: Sequence[Resort]
    ) -> dict[str, Drive]:
        """Return the drive to the closest access point per resort key."""
        access = [(r.key, a) for r in resorts for a in r.access]
        if not access:
            return {}
        places = [origin, *((a.lat, a.lon) for _, a in access)]
        coordinates = ";".join(f"{lon},{lat}" for lat, lon in places)  # lon first
        try:
            async with self._session.get(
                URL.format(coordinates=coordinates),
                params={"sources": "0", "annotations": "duration,distance"},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                response.raise_for_status()
                payload = await response.json()
        except (aiohttp.ClientError, TimeoutError) as error:
            raise SkiApiConnectionError(describe("OSRM", error)) from error
        try:
            return _closest(access, payload)
        except (KeyError, IndexError, TypeError, ValueError) as error:
            msg = f"OSRM: {error}"
            raise SkiApiParseError(msg) from error


def _closest(access: list[tuple[str, AccessPoint]], payload: dict) -> dict[str, Drive]:
    """Pick the shortest drive per resort; unreachable points (None) are skipped."""
    if payload.get("code") != "Ok":
        raise ValueError(payload.get("message") or payload.get("code"))
    # row 0 = from home; column 0 is home itself
    durations = payload["durations"][0][1:]
    distances = payload["distances"][0][1:]
    best: dict[str, Drive] = {}
    for (key, point), seconds, metres in zip(access, durations, distances, strict=True):
        if seconds is None or metres is None:
            continue
        drive = Drive(point.name, round(seconds / 60), round(metres / 1000, 1))
        if key not in best or drive.duration_min < best[key].duration_min:
            best[key] = drive
    return best
