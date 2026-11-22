"""Weather forecasts from the Open-Meteo API."""

import asyncio
from collections import defaultdict
from datetime import date, datetime
from statistics import median

import aiohttp

from custom_components.ski_resort_recommender.lib.errors import (
    SkiApiConnectionError,
    SkiApiParseError,
)
from custom_components.ski_resort_recommender.lib.models import DayForecast, Resort

URL = "https://api.open-meteo.com/v1/forecast"
TIMEZONE = "Europe/Zurich"
MODEL = "meteoswiss_icon_seamless"
DAILY = [
    "temperature_2m_min",
    "temperature_2m_max",
    "snowfall_sum",
    "sunshine_duration",
    "wind_speed_10m_max",
    "weather_code",
]
# MeteoSwiss ICON has no visibility in Open-Meteo; DWD ICON has it (hourly, metres,
# about 5 days ahead). Later days come back as None.
VISIBILITY_MODEL = "icon_seamless"
SKI_HOURS = range(9, 17)  # hourly values from 09:00 to 16:00 local time


class OpenMeteoProvider:
    """Fetch daily forecasts for all resorts in one batched request."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        """Use the injected aiohttp session (HA: async_get_clientsession)."""
        self._session = session

    async def get_forecast(
        self, resorts: list[Resort], days: int = 10
    ) -> dict[str, list[DayForecast]]:
        """Get the weather forecast for the list of ski resorts in our data."""
        coordinates = {
            "latitude": ",".join(str(r.lat) for r in resorts),
            "longitude": ",".join(str(r.lon) for r in resorts),
            "forecast_days": days,
            "timezone": TIMEZONE,
        }
        # two models -> two requests, each batched over all resorts
        daily, hourly = await asyncio.gather(
            self._get({**coordinates, "daily": ",".join(DAILY), "models": MODEL}),
            self._get(
                {**coordinates, "hourly": "visibility", "models": VISIBILITY_MODEL}
            ),
        )
        return _combine(resorts, daily, hourly)

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


def _combine(
    resorts: list[Resort], daily: list[dict], hourly: list[dict]
) -> dict[str, list[DayForecast]]:
    """Match both responses to the resorts by position and build the forecasts."""
    if not len(daily) == len(hourly) == len(resorts):
        msg = "Location count differs Resort count"
        raise SkiApiParseError(msg)

    try:
        return {
            resort.key: _parse_daily(
                day_loc["daily"], _ski_hours_visibility(hour_loc["hourly"])
            )
            for resort, day_loc, hour_loc in zip(resorts, daily, hourly, strict=True)
        }
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise SkiApiParseError(str(error)) from error


def _parse_daily(d: dict, visibility: dict[date, float]) -> list[DayForecast]:
    """Turn the `daily` block of one location into DayForecasts."""
    days = [date.fromisoformat(t) for t in d["time"]]
    return [
        DayForecast(
            day=day,
            temp_min_c=d["temperature_2m_min"][i],
            temp_max_c=d["temperature_2m_max"][i],
            snowfall_cm=d["snowfall_sum"][i],
            sunshine_hours=(d["sunshine_duration"][i] or 0) / 3600,  # api gives seconds
            wind_max_kmh=d["wind_speed_10m_max"][i],
            weather_code=d["weather_code"][i],
            visibility_m=visibility.get(day),
        )
        for i, day in enumerate(days)
    ]


def _ski_hours_visibility(h: dict) -> dict[date, float]:
    """Median visibility (metres) per day over the ski hours; skips missing values."""
    per_day: dict[date, list[float]] = defaultdict(list)
    for time, value in zip(h["time"], h["visibility"], strict=True):
        moment = datetime.fromisoformat(time)
        if value is not None and moment.hour in SKI_HOURS:
            per_day[moment.date()].append(value)
    return {day: median(values) for day, values in per_day.items()}
