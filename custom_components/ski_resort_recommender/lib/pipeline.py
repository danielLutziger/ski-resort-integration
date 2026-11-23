"""One update: forecasts, train connections and ranking (used by HA and the script)."""

from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

from custom_components.ski_resort_recommender.lib.errors import SkiApiError
from custom_components.ski_resort_recommender.lib.ev import BfeProvider, attach_chargers
from custom_components.ski_resort_recommender.lib.models import (
    Charger,
    Connection,
    Drive,
    Forecasts,
)
from custom_components.ski_resort_recommender.lib.open_meteo import (
    SKI_HOURS,
    OpenMeteoProvider,
)
from custom_components.ski_resort_recommender.lib.osrm import OsrmProvider
from custom_components.ski_resort_recommender.lib.sbb import SbbProvider
from custom_components.ski_resort_recommender.lib.service import (
    RecommendationResult,
    attach_connections,
    pick_recommendations,
)
from custom_components.ski_resort_recommender.lib.settings import CAR, TRAIN
from custom_components.ski_resort_recommender.lib.slf import SlfProvider
from custom_components.ski_resort_recommender.lib.snow_depth import (
    apply_measured_depth,
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
    # measured snow depth per SLF station, fetched together with the forecast
    snow_depths: dict[str, float] = field(default_factory=dict)
    # drive per resort key; fetched once a day per home location
    drives: dict[str, Drive] = field(default_factory=dict)
    drives_for: tuple[date, tuple[float, float]] | None = None
    # public EV chargers near the access points (electric car); once a day
    chargers: list[Charger] = field(default_factory=list)
    chargers_on: date | None = None


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
    errors only cost the connection of that resort. The measured snow depth (SLF)
    replaces the model's base; SLF errors keep the last values. Drive times (car
    mode) come once a day; OSRM errors keep the last ones. Electric car: public
    chargers (BFE) once a day, errors keep the last ones.
    connections_for: how many ranked results get their exact connection
    (default max_results; the outlook always gets one).
    """
    today = now.date()
    forecasts = await _forecasts(session, resorts, settings, now, cache)
    forecasts = apply_measured_depth(resorts, forecasts, cache.snow_depths, today)
    sbb = SbbProvider(session)
    await _refresh_travel(sbb, resorts, settings, today, cache)
    await _refresh_drives(session, resorts, settings, today, cache)
    drives = cache.drives
    if drives and settings.electric_car:
        await _refresh_chargers(session, resorts, today, cache)
        drives = attach_chargers(resorts, drives, cache.chargers)
    result = replace(
        pick_recommendations(
            resorts,
            forecasts,
            settings,
            today=today,
            travel=cache.travel,
            drives=drives,
        ),
        measured_snow_cm=dict(cache.snow_depths),
    )
    if not _by_train(settings):
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
    if not _by_train(settings):
        cache.travel = {}
        return
    reference = _reference_day(today, settings)
    if cache.fetched_on == today and cache.reference_day == reference:
        return
    cache.travel = (
        await sbb.connections(resorts, reference, settings) if reference else {}
    )
    cache.fetched_on, cache.reference_day = today, reference


async def _refresh_drives(
    session: aiohttp.ClientSession,
    resorts: list[Resort],
    settings: Settings,
    today: date,
    cache: Cache,
) -> None:
    """Fetch the drive times once a day (and when the home location changes)."""
    origin = settings.home_location
    if CAR not in settings.travel_modes or origin is None:
        cache.drives, cache.drives_for = {}, None
        return
    if cache.drives_for == (today, origin):
        return
    try:
        cache.drives = await OsrmProvider(session).drives(origin, resorts)
    except SkiApiError:
        return  # keep the last drive times, try again with the next update
    cache.drives_for = (today, origin)


async def _refresh_chargers(
    session: aiohttp.ClientSession, resorts: list[Resort], today: date, cache: Cache
) -> None:
    """Fetch the public chargers once a day; errors keep the last list."""
    if cache.chargers_on == today:
        return
    try:
        cache.chargers = await BfeProvider(session).chargers(resorts)
    except SkiApiError:
        return  # try again with the next update
    cache.chargers_on = today


def _by_train(settings: Settings) -> bool:
    """Train connections need the train mode and a home station."""
    return TRAIN in settings.travel_modes and bool(settings.home_station)


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
    cache.snow_depths = await _snow_depths(session, resorts, now, cache.snow_depths)
    return forecasts


async def _snow_depths(
    session: aiohttp.ClientSession,
    resorts: list[Resort],
    now: datetime,
    last: dict[str, float],
) -> dict[str, float]:
    """Measured snow depth per station at today's opening; the last one on errors."""
    codes = {s.code for resort in resorts for s in resort.snow_stations}
    if not codes:
        return {}
    opening = now.replace(hour=SKI_HOURS.start, minute=0, second=0, microsecond=0)
    try:
        return await SlfProvider(session).snow_depths(codes, opening)
    except SkiApiError:
        return last  # the forecast still works with the last (or model) depth


def _reference_day(today: date, settings: Settings) -> date | None:
    """Return the next allowed ski day after today (within the outlook window)."""
    for offset in range(1, settings.outlook_days + 1):
        day = today + timedelta(days=offset)
        if day.weekday() in settings.allowed_weekdays:
            return day
    return None
