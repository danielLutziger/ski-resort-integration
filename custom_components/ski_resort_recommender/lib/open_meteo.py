"""Weather forecasts from the Open-Meteo API."""

from datetime import date

import aiohttp

from custom_components.ski_resort_recommender.lib.errors import (
    SkiApiConnectionError,
    SkiApiParseError,
)
from custom_components.ski_resort_recommender.lib.models import DayForecast, Resort

URL = "https://api.open-meteo.com/v1/forecast"
MODEL = "meteoswiss_icon_seamless"
DAILY = [
    "temperature_2m_min",
    "temperature_2m_max",
    "snowfall_sum",
    "sunshine_duration",
    "wind_speed_10m_max",
    "weather_code",
]


class OpenMeteoProvider:
    """Fetch daily forecasts for all resorts in one batched request."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        """Use the injected aiohttp session (HA: async_get_clientsession)."""
        self._session = session

    async def get_forecast(
        self, resorts: list[Resort], days: int = 10
    ) -> dict[str, list[DayForecast]]:
        """Get the weather forecast for the list of ski resorts in our data."""
        params = {
            "latitude": ",".join(str(r.lat) for r in resorts),
            "longitude": ",".join(str(r.lon) for r in resorts),
            "daily": ",".join(DAILY),
            "models": MODEL,
            "forecast_days": days,
            "timezone": "Europe/Zurich",
        }

        try:
            async with self._session.get(
                URL, params=params, timeout=aiohttp.ClientTimeout(total=15)
            ) as response:
                response.raise_for_status()
                payload = await response.json()
        except (aiohttp.ClientError, TimeoutError) as error:
            raise SkiApiConnectionError(str(error)) from error

        # we would expect mutliple resorts to be returned, if from it
        locations = payload if isinstance(payload, list) else [payload]
        if len(locations) != len(resorts):
            msg = "Location count differs Resort count"
            raise SkiApiParseError(msg)

        try:
            return {
                resort.key: _parse_daily(loc["daily"])
                for resort, loc in zip(resorts, locations, strict=True)
            }
        except (KeyError, IndexError, TypeError, ValueError) as error:
            raise SkiApiParseError(str(error)) from error


def _parse_daily(d: dict) -> list[DayForecast]:
    """Turn the `daily` block of one location into DayForecasts."""
    return [
        DayForecast(
            day=date.fromisoformat(d["time"][i]),
            temp_min_c=d["temperature_2m_min"][i],
            temp_max_c=d["temperature_2m_max"][i],
            snowfall_cm=d["snowfall_sum"][i],
            sunshine_hours=(d["sunshine_duration"][i] or 0) / 3600,  # api gives seconds
            wind_max_kmh=d["wind_speed_10m_max"][i],
            weather_code=d["weather_code"][i],
            vision=None,
        )
        for i in range(len(d["time"]))
    ]
