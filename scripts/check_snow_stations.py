"""
Check the SLF snow stations of every resort: depth now, wind, biggest drop (3 days).

A station the wind blows bare loses a lot of snow in one windy night while its
neighbours keep theirs (23.11: Rientallücke 27 -> 1 cm). Such stations do not
represent the pistes: replace them in the resort file.

Run from the repo root: python -m scripts.check_snow_stations
"""

import asyncio
from pathlib import Path

import aiohttp

from custom_components.ski_resort_recommender.lib.resorts import load_resorts
from custom_components.ski_resort_recommender.lib.slf import URL

RESORTS = Path("custom_components/ski_resort_recommender/resorts")
DROP_WARNING_CM = 15  # more than this within 3 days: probably wind erosion


async def station(session: aiohttp.ClientSession, code: str) -> list[dict]:
    """Return the 30 min values of the last 3 days ([] if the station has none)."""
    async with session.get(URL.format(code=code), params={"period_in_days": 3}) as r:
        return await r.json() if r.status == 200 else []  # noqa: PLR2004


def biggest_drop(depths: list[float]) -> float:
    """Return the largest loss from an earlier maximum (cm)."""
    top, drop = float("-inf"), 0.0
    for depth in depths:
        top = max(top, depth)
        drop = max(drop, top - depth)
    return drop


async def main() -> None:
    """Print every resort's stations with depth, wind and biggest drop."""
    resorts = load_resorts(RESORTS)
    async with aiohttp.ClientSession() as session:
        for resort in resorts:
            print(resort.name if resort.snow_stations else f"{resort.name}: model only")
            for s in resort.snow_stations:
                rows = await station(session, s.code)
                hs = [r["HS"] for r in rows if r.get("HS") is not None]
                gusts = [r["VW_30MIN_MAX"] for r in rows if r.get("VW_30MIN_MAX")]
                if not hs:
                    print(f"  {s.code:<5} {s.name:<22} NO DATA")
                    continue
                drop = biggest_drop(hs)
                warn = "  <- wind erosion?" if drop > DROP_WARNING_CM else ""
                gust = f"{max(gusts):4.1f} m/s" if gusts else "    -"
                print(
                    f"  {s.code:<5} {s.name:<22} {s.elevation_m} m"
                    f"  now {hs[-1]:4.0f} cm  max gust {gust}"
                    f"  biggest drop {drop:3.0f} cm{warn}"
                )


if __name__ == "__main__":
    asyncio.run(main())
