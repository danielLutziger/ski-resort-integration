"""
Run the whole chain against the real APIs and print the ranking.

python -m scripts.try_forecast [--from STATION] [--all]
  --from  home station for the train connections (no travel score without it)
  --all   every weekday and up to 200 results instead of the defaults
"""

import argparse
import asyncio
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import aiohttp

from custom_components.ski_resort_recommender.lib.open_meteo import OpenMeteoProvider
from custom_components.ski_resort_recommender.lib.resorts import load_resorts
from custom_components.ski_resort_recommender.lib.sbb import SbbProvider
from custom_components.ski_resort_recommender.lib.service import (
    Recommendation,
    attach_connections,
    pick_recommendations,
)
from custom_components.ski_resort_recommender.lib.settings import Settings


async def main() -> None:
    """Fetch forecasts and connections, pick recommendations, print them."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--from", dest="home_station")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()

    settings = Settings(home_station=args.home_station)
    if args.all:  # override the defaults in the script, never in Settings
        settings = replace(
            settings, allowed_weekdays=frozenset(range(7)), max_results=200
        )
    resorts = load_resorts(
        Path("custom_components/ski_resort_recommender/resorts.yaml")
    )
    today = date.today()  # noqa: DTZ011
    async with aiohttp.ClientSession() as session:
        forecasts = await OpenMeteoProvider(session).get_forecast(resorts)
        sbb = SbbProvider(session)
        # travel times from one reference day: the next allowed day
        reference = next(
            today + timedelta(days=n)
            for n in range(1, 8)
            if (today + timedelta(days=n)).weekday() in settings.allowed_weekdays
        )
        travel = await sbb.connections(resorts, reference, settings)
        result = pick_recommendations(
            resorts, forecasts, settings, today=today, travel=travel
        )
        # the exact connection of each recommended day
        shown = [*result.recommendations[:5], *filter(None, [result.outlook])]
        exact = {}
        if settings.home_station:
            for r in shown:
                if r.resort.station:
                    c = await sbb.connection(r.resort.station, r.day.day, settings)
                    if c:
                        exact[(r.resort.key, r.day.day)] = c
        result = attach_connections(result, exact)

    print(f"Status: {result.status}  (travel reference day {reference:%a %d.%m})")
    for r in result.recommendations:
        print_line(r)
    if result.outlook:
        print("Outlook:")
        print_line(result.outlook)


def print_line(r: Recommendation) -> None:
    """Print one recommendation with its score reasons and train connection."""
    reasons = {key: round(value, 1) for key, value in r.score.reasons.items()}
    print(
        f"{r.day.day:%a %d.%m}  {r.resort.name:<26} {r.point.name:<18} "
        f"{r.score.total:5.1f}  {'GOOD' if r.is_good else '----'}  {reasons}"
    )
    if c := r.connection:
        legs = ", ".join(
            f"{leg.line}"
            + (f" ({leg.train_number})" if leg.train_number else "")
            + f" {leg.departure:%H:%M} {leg.departure_station}"
            + (f" pl. {leg.platform}" if leg.platform else "")
            + f" -> {leg.arrival:%H:%M} {leg.arrival_station}"
            for leg in c.legs
        )
        print(
            f"      train: dep {c.departure:%a %H:%M} pl. {c.platform or '-'}, "
            f"arr {c.arrival:%H:%M}, {c.duration_min} min, {c.transfers} changes: "
            f"{legs}"
        )


asyncio.run(main())
