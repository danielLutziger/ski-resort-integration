"""One update: forecasts, train connections and ranking (used by HA and the script)."""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

from custom_components.ski_resort_recommender.lib.errors import SkiApiError
from custom_components.ski_resort_recommender.lib.models import Connection, Forecasts
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
class Cache:
    """What an update keeps for the next ones (in memory)."""

    # SBB travel times per resort, fetched once a day for one reference day
    fetched_on: date | None = None
    reference_day: date | None = None
    travel: dict[str, Connection] = field(default_factory=dict)
    # last Open-Meteo forecast and when it was fetched
    forecasts: Forecasts | None = None
    forecasts_at: datetime | None = None


async def build_recommendations(  # noqa: PLR0913 (keyword-only inputs)
    session: aiohttp.ClientSession,
    resorts: list[Resort],
    settings: Settings,
    *,
    now: datetime,
    cache: Cache,
    connections_for: int | None = None,
) -> RecommendationResult:
    """
    Fetch forecasts, rank, and attach the morning connection of each shown result.

    now: local time; today is now.date(). The forecast is fetched at most every
    settings.weather_interval. Weather errors (SkiApiError) reach the caller,
    unless a forecast younger than settings.weather_max_age is cached. Train
    errors only cost the connection of that resort.
    connections_for: how many ranked results get their exact connection
    (default max_results; the outlook always gets one).
    """
    today = now.date()
    forecasts = await _forecasts(session, resorts, settings, now, cache)
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
    cache: Cache,
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


async def _forecasts(
    session: aiohttp.ClientSession,
    resorts: list[Resort],
    settings: Settings,
    now: datetime,
    cache: Cache,
) -> Forecasts:
    """Return the cached forecast within weather_interval, else fetch a new one."""
    age = now - cache.forecasts_at if cache.forecasts_at else None
    cached = cache.forecasts is not None and age is not None
    if cached and age < settings.weather_interval:
        return cache.forecasts
    try:
        forecasts = await OpenMeteoProvider(session).get_forecast(resorts)
    except SkiApiError:
        if cached and age < settings.weather_max_age:
            return cache.forecasts  # e.g. rate limited: keep the last one
        raise
    cache.forecasts, cache.forecasts_at = forecasts, now
    return forecasts


def _reference_day(today: date, settings: Settings) -> date | None:
    """Return the next allowed ski day after today (within the outlook window)."""
    for offset in range(1, settings.outlook_days + 1):
        day = today + timedelta(days=offset)
        if day.weekday() in settings.allowed_weekdays:
            return day
    return None
