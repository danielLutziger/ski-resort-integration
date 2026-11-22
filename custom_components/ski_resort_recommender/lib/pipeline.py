"""One update: forecasts, train connections and ranking (used by HA and the script)."""

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import TYPE_CHECKING

from custom_components.ski_resort_recommender.lib.errors import SkiApiError
from custom_components.ski_resort_recommender.lib.models import Connection
from custom_components.ski_resort_recommender.lib.open_meteo import OpenMeteoProvider
from custom_components.ski_resort_recommender.lib.sbb import SbbProvider
from custom_components.ski_resort_recommender.lib.service import (
    RecommendationResult,
    attach_connections,
    pick_recommendations,
)

if TYPE_CHECKING:
    import aiohttp

    from custom_components.ski_resort_recommender.lib.models import Resort
    from custom_components.ski_resort_recommender.lib.settings import Settings


@dataclass
class TravelCache:
    """Travel times per resort, fetched once a day for one reference day."""

    fetched_on: date | None = None
    reference_day: date | None = None
    travel: dict[str, Connection] = field(default_factory=dict)


async def build_recommendations(  # noqa: PLR0913 (keyword-only inputs)
    session: aiohttp.ClientSession,
    resorts: list[Resort],
    settings: Settings,
    *,
    today: date,
    cache: TravelCache,
    connections_for: int | None = None,
) -> RecommendationResult:
    """
    Fetch forecasts, rank, and attach the morning connection of each shown result.

    Weather errors (SkiApiError) reach the caller: without forecasts there is
    nothing to rank. Train errors only cost the connection of that resort.
    connections_for: how many ranked results get their exact connection
    (default max_results; the outlook always gets one).
    """
    forecasts = await OpenMeteoProvider(session).get_forecast(resorts)
    sbb = SbbProvider(session)
    await _refresh_travel(sbb, resorts, settings, today, cache)
    result = pick_recommendations(
        resorts, forecasts, settings, today=today, travel=cache.travel
    )
    if not settings.home_station:
        return result

    limit = settings.max_results if connections_for is None else connections_for
    shown = [*result.recommendations[:limit], *filter(None, [result.outlook])]
    exact = {}
    for r in shown:
        if not r.resort.station:
            continue
        try:
            connection = await sbb.connection(r.resort.station, r.day.day, settings)
        except SkiApiError:
            continue  # keep the reference connection
        if connection:
            exact[(r.resort.key, r.day.day)] = connection
    return attach_connections(result, exact)


async def _refresh_travel(
    sbb: SbbProvider,
    resorts: list[Resort],
    settings: Settings,
    today: date,
    cache: TravelCache,
) -> None:
    """Fetch the travel times for the next allowed day, at most once a day."""
    if not settings.home_station:
        cache.travel = {}
        return
    reference = _reference_day(today, settings)
    if cache.fetched_on == today and cache.reference_day == reference:
        return
    cache.travel = (
        await sbb.connections(resorts, reference, settings) if reference else {}
    )
    cache.fetched_on, cache.reference_day = today, reference


def _reference_day(today: date, settings: Settings) -> date | None:
    """Return the next allowed ski day after today (within the outlook window)."""
    for offset in range(1, settings.outlook_days + 1):
        day = today + timedelta(days=offset)
        if day.weekday() in settings.allowed_weekdays:
            return day
    return None
