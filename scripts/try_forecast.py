import asyncio
from pathlib import Path
import aiohttp

from custom_components.ski_resort_recommender.lib.resorts import load_resorts
from custom_components.ski_resort_recommender.lib.open_meteo import OpenMeteoProvider


async def main():
    resorts = load_resorts(
        Path("custom_components/ski_resort_recommender/resorts.yaml")
    )
    async with aiohttp.ClientSession() as session:
        forecasts = await OpenMeteoProvider(session).get_forecast(resorts)

    for resort in resorts:
        print(resort.name)
        for day in forecasts[resort.key]:
            print(
                f"  {day.day}  {day.temp_min_c}..{day.temp_max_c} °C  "
                f"snow {day.snowfall_cm} cm  sun {day.sunshine_hours:.1f} h  wind {day.wind_max_kmh} km/h"
            )


asyncio.run(main())
