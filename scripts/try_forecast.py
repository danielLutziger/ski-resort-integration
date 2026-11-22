"""Run the whole chain against the real API and print the ranking."""

import asyncio
from pathlib import Path

import aiohttp

from custom_components.ski_resort_recommender.lib.open_meteo import OpenMeteoProvider
from custom_components.ski_resort_recommender.lib.resorts import load_resorts
from custom_components.ski_resort_recommender.lib.service import (
    Recommendation,
    pick_recommendations,
)
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
    print(f"Status: {result.status}")

    for r in result.recommendations:
        print_line(r)
    if result.outlook:
        print("Outlook:")
        print_line(result.outlook)


def print_line(r: Recommendation) -> None:
    """Print one recommendation with its score reasons."""
    reasons = {key: round(value, 1) for key, value in r.score.reasons.items()}
    print(
        f"{r.day.day:%a %d.%m}  {r.resort.name:<26} {r.point.name:<18} "
        f"{r.score.total:5.1f}  {'GOOD' if r.is_good else '----'}  {reasons}"
    )


asyncio.run(main())
