"""Measured snow depth from the SLF IMIS stations (open data, CC BY 4.0)."""

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING

import aiohttp

from custom_components.ski_resort_recommender.lib.errors import (
    SkiApiConnectionError,
    SkiApiError,
    SkiApiParseError,
    describe,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

URL = "https://measurement-api.slf.ch/public/api/imis/station/{code}/measurements"
# the licence asks for a visible reference with a link
ATTRIBUTION = "WSL Institute for Snow and Avalanche Research SLF"
ATTRIBUTION_URL = "https://www.slf.ch"
MAX_PARALLEL = 4  # be gentle with the free API


class SlfProvider:
    """Fetch the measured snow depth (HS) of IMIS stations, one request each."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        """Use the injected aiohttp session (HA: async_get_clientsession)."""
        self._session = session
        self._limit = asyncio.Semaphore(MAX_PARALLEL)

    async def snow_depths(
        self, codes: Iterable[str], reference: datetime
    ) -> dict[str, float]:
        """
        Return the snow depth (cm) per station, measured closest to reference.

        Stations without a value or with a failed request are left out; only
        when every request fails the first error is raised.
        """
        codes = sorted(set(codes))
        results = await asyncio.gather(
            *(self._station(code, reference) for code in codes),
            return_exceptions=True,
        )
        for result in results:  # programming errors are not API errors
            if isinstance(result, BaseException) and not isinstance(
                result, SkiApiError
            ):
                raise result
        errors = [r for r in results if isinstance(r, SkiApiError)]
        if codes and len(errors) == len(codes):
            raise errors[0]
        return {
            code: depth
            for code, depth in zip(codes, results, strict=True)
            if isinstance(depth, float)
        }

    async def _station(self, code: str, reference: datetime) -> float | None:
        """Fetch the last 24 h of one station and pick the depth."""
        async with self._limit:
            try:
                async with self._session.get(
                    URL.format(code=code),
                    params={"period_in_days": 1},
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as response:
                    response.raise_for_status()
                    payload = await response.json()
            except (aiohttp.ClientError, TimeoutError) as error:
                raise SkiApiConnectionError(describe("SLF", error)) from error
        try:
            return _depth_at(payload, reference)
        except (KeyError, TypeError, ValueError, AttributeError) as error:
            msg = f"SLF {code}: {error}"
            raise SkiApiParseError(msg) from error


def _depth_at(rows: list[dict], reference: datetime) -> float | None:
    """HS (cm, at least 0) of the measurement closest to reference; None if none."""
    measured = [
        (abs(datetime.fromisoformat(row["measure_date"]) - reference), row["HS"])
        for row in rows
        if row.get("HS") is not None
    ]
    if not measured:
        return None
    _, depth = min(measured, key=lambda m: m[0])
    return max(float(depth), 0.0)
