"""Morning train connections from transport.opendata.ch (SBB timetable)."""

import asyncio
from datetime import date, datetime
from typing import TYPE_CHECKING

import aiohttp

from custom_components.ski_resort_recommender.lib.errors import (
    SkiApiConnectionError,
    SkiApiError,
    SkiApiParseError,
)
from custom_components.ski_resort_recommender.lib.models import Connection, Leg

if TYPE_CHECKING:
    from custom_components.ski_resort_recommender.lib.models import Resort
    from custom_components.ski_resort_recommender.lib.settings import Settings

URL = "https://transport.opendata.ch/v1/connections"
LIMIT = 6  # connections arriving before arrival_latest, enough to cover the window
MAX_PARALLEL = 4  # be gentle with the free API
# not trains: their journey "name" is an internal trip id, not a train number
NO_TRAIN_NUMBER = {"B", "BUS", "NFB", "KB", "EXB", "T", "TRAM", "M", "BAT", "FUN", "PB"}


class SbbProvider:
    """Find the morning connection from the home station to each resort."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        """Use the injected aiohttp session (HA: async_get_clientsession)."""
        self._session = session
        self._limit = asyncio.Semaphore(MAX_PARALLEL)

    async def connection(
        self, to_station: str, day: date, settings: Settings
    ) -> Connection | None:
        """Return the connection arriving in the arrival window on day, or None."""
        params = {
            "from": settings.home_station,
            "to": to_station,
            "date": day.isoformat(),
            "time": settings.arrival_latest.strftime("%H:%M"),
            "isArrivalTime": 1,
            "limit": LIMIT,
        }
        try:
            async with (
                self._limit,
                self._session.get(
                    URL, params=params, timeout=aiohttp.ClientTimeout(total=20)
                ) as response,
            ):
                response.raise_for_status()
                payload = await response.json()
        except (aiohttp.ClientError, TimeoutError) as error:
            raise SkiApiConnectionError(str(error)) from error
        return _pick(_parse(payload), day, settings)

    async def connections(
        self, resorts: list[Resort], day: date, settings: Settings
    ) -> dict[str, Connection]:
        """
        Return one connection per resort key.

        Resorts without station or connection are left out; one failing request
        does not break the others.
        """
        if not settings.home_station:
            return {}
        with_station = [r for r in resorts if r.station]
        results = await asyncio.gather(
            *(self.connection(r.station, day, settings) for r in with_station),
            return_exceptions=True,
        )
        found = {}
        for resort, result in zip(with_station, results, strict=True):
            if isinstance(result, Connection):
                found[resort.key] = result
            elif isinstance(result, BaseException) and not isinstance(
                result, SkiApiError
            ):
                raise result
        return found


def _parse(payload: dict) -> list[Connection]:
    """Turn the API response into Connections (walks between stops are skipped)."""
    try:
        return [_connection(c) for c in payload["connections"]]
    except (KeyError, TypeError, ValueError) as error:
        raise SkiApiParseError(str(error)) from error


def _connection(c: dict) -> Connection:
    """One connection of the response."""
    days, clock = c["duration"].split("d")
    hours, minutes, _ = clock.split(":")
    return Connection(
        departure=_time(c["from"]["departure"]),
        platform=c["from"]["platform"] or None,
        arrival=_time(c["to"]["arrival"]),
        duration_min=int(days) * 24 * 60 + int(hours) * 60 + int(minutes),
        transfers=c["transfers"],
        legs=tuple(_leg(s) for s in c["sections"] if s.get("journey")),
    )


def _leg(section: dict) -> Leg:
    """One ride: line (category + number), train number, stations, times."""
    journey = section["journey"]
    is_train = journey["category"] not in NO_TRAIN_NUMBER
    return Leg(
        line=f"{journey['category']} {journey['number']}".strip(),
        train_number=(journey["name"].lstrip("0") or None) if is_train else None,
        departure_station=section["departure"]["station"]["name"],
        departure=_time(section["departure"]["departure"]),
        platform=section["departure"]["platform"] or None,
        arrival_station=section["arrival"]["station"]["name"],
        arrival=_time(section["arrival"]["arrival"]),
    )


def _time(value: str) -> datetime:
    """Parse the API time stamp, e.g. 2026-11-28T07:07:00+0100."""
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S%z")


def _pick(
    connections: list[Connection], day: date, settings: Settings
) -> Connection | None:
    """Leaving on day, arriving in the window; closest to the target wins."""
    candidates = [
        c
        for c in connections
        if c.departure.date() == day
        and settings.arrival_earliest <= c.arrival.time() <= settings.arrival_latest
    ]
    target = datetime.combine(day, settings.arrival_target)

    def distance(c: Connection) -> float:
        return abs((c.arrival.replace(tzinfo=None) - target).total_seconds())

    return min(candidates, key=distance, default=None)
