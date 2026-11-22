"""Run the whole chain against the real API and print the ranking."""

import asyncio
from pathlib import Path

import aiohttp

from custom_components.ski_resort_recommender.lib.open_meteo import OpenMeteoProvider
from custom_components.ski_resort_recommender.lib.resorts import load_resorts
from custom_components.ski_resort_recommender.lib.service import pick_recommendations
from custom_components.ski_resort_recommender.lib.settings import Settings


async def main() -> None:
    """Fetch forecasts, pick recommendations, print them."""
    resorts = load_resorts(
        Path("custom_components/ski_resort_recommender/resorts.yaml")
    )
    async with aiohttp.ClientSession() as session:
        forecasts = await OpenMeteoProvider(session).get_forecast(resorts)

    # override the defaults to see every fetched day, not just the top 3 weekend days
    settings = Settings(allowed_weekdays=frozenset(range(7)), max_results=200)
    result = pick_recommendations(resorts, forecasts, settings)
    print("Good day found" if result.has_good_day else "No good day")

    for r in result.recommendations:
        print(
            f"{r.day.day:%a %d.%m}  {r.resort.name:<14} {r.score.total:5.1f}  "
            f"{'GOOD' if r.is_good else '----'}  {r.score.reasons}"
        )


asyncio.run(main())
