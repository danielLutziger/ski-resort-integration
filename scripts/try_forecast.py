import asyncio
from pathlib import Path
import aiohttp

from custom_components.ski_resort_recommender.lib.open_meteo import OpenMeteoProvider
from custom_components.ski_resort_recommender.lib.resorts import load_resorts
from custom_components.ski_resort_recommender.lib.service import pick_recommendations
from custom_components.ski_resort_recommender.lib.settings import Settings


async def main():
    resorts = load_resorts(
        Path("custom_components/ski_resort_recommender/resorts.yaml")
    )
    async with aiohttp.ClientSession() as session:
        forecasts = await OpenMeteoProvider(session).get_forecast(resorts)

    result = pick_recommendations(
        resorts=resorts, forecasts=forecasts, settings=Settings(), today=None
    )
    print("Good day found" if result.has_good_day else "No good day")

    for r in result.recommendations:
        print(
            f"{r.day.day:%a %d.%m}  {r.resort.name:<14} {r.score.total:5.1f}  "
            f"{'GOOD' if r.is_good else '----'}  {r.score.reasons}"
        )


asyncio.run(main())
