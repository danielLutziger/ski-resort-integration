"""Weather forecasts from the Open-Meteo API."""

import asyncio
from collections import defaultdict
from dataclasses import replace
from datetime import date, datetime, timedelta
from statistics import mean, median
from typing import TYPE_CHECKING

import aiohttp

from custom_components.ski_resort_recommender.lib.errors import (
    SkiApiConnectionError,
    SkiApiParseError,
)
from custom_components.ski_resort_recommender.lib.models import (
    DayForecast,
    Forecasts,
    Resort,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

URL = "https://api.open-meteo.com/v1/forecast"
TIMEZONE = "Europe/Zurich"
MODEL = "meteoswiss_icon_seamless"
DAILY = [
    "temperature_2m_min",
    "temperature_2m_max",
    "snowfall_sum",
    "sunshine_duration",
    "daylight_duration",
    "weather_code",
]
HOURLY = [
    "temperature_2m",
    "snowfall",
    "rain",
    "showers",
    "wind_gusts_10m",
    "weather_code",
    "snow_depth",
]
# DWD ICON fills what MeteoSwiss lacks: daily values after today + 4 (MeteoSwiss
# horizon) and hourly visibility (metres, about 5 days; MeteoSwiss has none).
FALLBACK_MODEL = "icon_seamless"
SKI_HOURS = range(9, 17)  # hourly values from 09:00 to 16:00 local time
# fresh snow and rain (icy slope) count in this window before the lifts open
BEFORE_OPENING = timedelta(hours=48)
RAIN = ("rain", "showers")  # liquid precipitation (mm)
RAIN_HOUR_MM = 0.1  # an hour with more liquid precipitation counts as a rain hour
PAST_DAYS = 2  # needed for the window before opening of tomorrow


class OpenMeteoProvider:
    """Fetch forecasts for every weather point of every resort, batched."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        """Use the injected aiohttp session (HA: async_get_clientsession)."""
        self._session = session

    async def get_forecast(self, resorts: list[Resort], days: int = 8) -> Forecasts:
        """Get the weather forecast for all points of the given resorts."""
        params = {
            **_coordinates(resorts),
            "forecast_days": days,
            "past_days": PAST_DAYS,
            "timezone": TIMEZONE,
            "daily": ",".join(DAILY),
        }
        # two models -> two requests, each batched over all points
        meteoswiss, dwd = await asyncio.gather(
            self._get({**params, "hourly": ",".join(HOURLY), "models": MODEL}),
            self._get(
                {
                    **params,
                    "hourly": ",".join([*HOURLY, "visibility"]),
                    "models": FALLBACK_MODEL,
                }
            ),
        )
        return _combine(resorts, meteoswiss, dwd)

    async def _get(self, params: dict) -> list[dict]:
        """Run one request; always return a list of locations."""
        try:
            async with self._session.get(
                URL, params=params, timeout=aiohttp.ClientTimeout(total=15)
            ) as response:
                response.raise_for_status()
                payload = await response.json()
        except (aiohttp.ClientError, TimeoutError) as error:
            raise SkiApiConnectionError(str(error)) from error

        # one location comes back as an object, several as a list
        return payload if isinstance(payload, list) else [payload]


def _coordinates(resorts: list[Resort]) -> dict[str, str]:
    """Request parameters with one location per point, resort by resort."""
    points = [point for resort in resorts for point in resort.points]
    return {
        "latitude": ",".join(str(p.lat) for p in points),
        "longitude": ",".join(str(p.lon) for p in points),
        "elevation": ",".join(str(p.elevation_m) for p in points),
    }


def _combine(
    resorts: list[Resort], meteoswiss: list[dict], dwd: list[dict]
) -> Forecasts:
    """Match both responses to the points by position and build the forecasts."""
    pairs = [(resort, point) for resort in resorts for point in resort.points]
    if not len(meteoswiss) == len(dwd) == len(pairs):
        msg = "Location count differs from point count"
        raise SkiApiParseError(msg)

    forecasts: Forecasts = {resort.key: {} for resort in resorts}
    try:
        for (resort, point), ms_loc, dwd_loc in zip(
            pairs, meteoswiss, dwd, strict=True
        ):
            visibility = _ski_hours(dwd_loc["hourly"], "visibility", median)
            forecasts[resort.key][point.name] = _merge(
                _parse_location(ms_loc, visibility),
                _parse_location(dwd_loc, visibility),
            )
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise SkiApiParseError(str(error)) from error
    return forecasts


def _merge(meteoswiss: list[DayForecast], dwd: list[DayForecast]) -> list[DayForecast]:
    """Use MeteoSwiss where it has data and DWD for every other day."""
    by_day = {day.day: day for day in dwd}
    by_day.update({day.day: day for day in meteoswiss if day.has_data})
    return sorted(by_day.values(), key=lambda day: day.day)


def _parse_location(loc: dict, visibility: dict[date, float]) -> list[DayForecast]:
    """Daily values plus the ski-hours values of one location and one model."""
    h = loc["hourly"]
    temp_ski = _ski_hours(h, "temperature_2m", mean)
    gust_max = _ski_hours(h, "wind_gusts_10m", max)
    weather_codes = _ski_hours(h, "weather_code", tuple)
    snow_depth = _ski_hours(h, "snow_depth", _at_opening_cm)
    fresh_snow = _before_opening(h, ("snowfall",))
    recent_rain = _before_opening(h, RAIN)
    snow_after_rain = _snow_after_rain(h)
    return [
        replace(
            day,
            temp_ski_c=temp_ski.get(day.day),
            gust_max_kmh=gust_max.get(day.day),
            fresh_snow_cm=fresh_snow.get(day.day),
            weather_codes_ski=weather_codes.get(day.day, ()),
            snow_depth_cm=snow_depth.get(day.day),
            recent_rain_mm=recent_rain.get(day.day),
            snow_after_rain_cm=snow_after_rain.get(day.day),
        )
        for day in _parse_daily(loc["daily"], visibility=visibility)
    ]


def _parse_daily(
    d: dict, *, visibility: dict[date, float] | None = None
) -> list[DayForecast]:
    """Turn the `daily` block into DayForecasts (hourly values are added later)."""
    days = [date.fromisoformat(t) for t in d["time"]]
    return [
        DayForecast(
            day=day,
            temp_min_c=d["temperature_2m_min"][i],
            temp_max_c=d["temperature_2m_max"][i],
            snowfall_cm=d["snowfall_sum"][i],
            sunshine_hours=_seconds_to_hours(d["sunshine_duration"][i]),
            daylight_hours=_seconds_to_hours(d["daylight_duration"][i]),
            weather_code=d["weather_code"][i],
            visibility_m=(visibility or {}).get(day),
            temp_ski_c=None,
            gust_max_kmh=None,
            fresh_snow_cm=None,
        )
        for i, day in enumerate(days)
    ]


def _seconds_to_hours(seconds: float | None) -> float | None:
    """Convert the API's durations; keep None (no forecast) as None."""
    return None if seconds is None else seconds / 3600


def _hours(h: dict, key: str) -> Iterable[tuple[datetime, float]]:
    """Yield (time, value) of one hourly variable, skipping missing values."""
    for time, value in zip(h["time"], h[key], strict=True):
        if value is not None:
            yield datetime.fromisoformat(time), value


def _ski_hours[T](
    h: dict, key: str, aggregate: Callable[[list[float]], T]
) -> dict[date, T]:
    """Aggregate one hourly variable per day over the ski hours."""
    per_day: dict[date, list[float]] = defaultdict(list)
    for moment, value in _hours(h, key):
        if moment.hour in SKI_HOURS:
            per_day[moment.date()].append(value)
    return {day: aggregate(values) for day, values in per_day.items()}


def _at_opening_cm(depths_m: list[float]) -> float:
    """Snow depth at the first ski hour (09:00), converted from m to cm."""
    return depths_m[0] * 100


def _per_hour(h: dict, keys: tuple[str, ...]) -> dict[datetime, float]:
    """Sum of several hourly variables per hour (missing values count as 0)."""
    per_hour: dict[datetime, float] = defaultdict(float)
    for key in keys:
        for moment, value in _hours(h, key):
            per_hour[moment] += value
    return per_hour


def _opening_windows(h: dict) -> dict[date, tuple[datetime, datetime]]:
    """
    Return the 48 h window (start, opening] per day that has a full window.

    Hourly sums belong to the hour before their time stamp: the 09:00 value is
    the amount from 08:00 to 09:00, so it still counts as before opening.
    """
    times = [datetime.fromisoformat(t) for t in h["time"]]
    windows = {}
    for day in sorted({t.date() for t in times}):
        opening = datetime.combine(day, datetime.min.time()).replace(
            hour=SKI_HOURS.start
        )
        start = opening - BEFORE_OPENING
        if times[0] <= start + timedelta(hours=1):  # the series sees the whole window
            windows[day] = (start, opening)
    return windows


def _before_opening(h: dict, keys: tuple[str, ...]) -> dict[date, float]:
    """Sum of hourly variables in the 48 h before opening."""
    per_hour = _per_hour(h, keys)
    return {
        day: sum(v for moment, v in per_hour.items() if start < moment <= opening)
        for day, (start, opening) in _opening_windows(h).items()
    }


def _snow_after_rain(h: dict) -> dict[date, float]:
    """Snowfall (cm) after the last rain hour before opening: it covers the ice."""
    rain = _per_hour(h, RAIN)
    snow = _per_hour(h, ("snowfall",))
    result = {}
    for day, (start, opening) in _opening_windows(h).items():
        rain_hours = [
            m for m, v in rain.items() if start < m <= opening and v > RAIN_HOUR_MM
        ]
        after = max(rain_hours, default=start)  # no rain: all snow lies on top
        result[day] = sum(v for m, v in snow.items() if after < m <= opening)
    return result
