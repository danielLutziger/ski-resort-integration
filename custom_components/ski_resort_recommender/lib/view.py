"""What the sensor shows: headline, one entry per recommendation, Markdown table."""

from typing import TYPE_CHECKING

from custom_components.ski_resort_recommender.lib.service import (
    Recommendation,
    RecommendationResult,
    RecommendationStatus,
)

if TYPE_CHECKING:
    from custom_components.ski_resort_recommender.lib.models import Connection

HEADLINES = {
    RecommendationStatus.GOOD_DAY: "Good day",
    RecommendationStatus.NO_GOOD_DAY: "No good day",
    RecommendationStatus.NO_FORECAST: "No forecast yet",
}
NO_VALUE = "-"


def headline(result: RecommendationResult) -> str:
    """Sensor state: Good day / No good day / No forecast yet."""
    return HEADLINES[result.status]


def entry(r: Recommendation, *, outlook: bool = False) -> dict:
    """One recommendation as plain values (sensor attribute, JSON friendly)."""
    offer = r.resort.snow_n_rail
    return {
        "classification": _classification(r, outlook=outlook),
        "score": round(r.score.total),
        "date": r.day.day.isoformat(),
        "day": f"{r.day.day:%a %d.%m}",
        "resort": r.resort.name,
        "point": r.point.name,
        "weather_icon": r.weather_icon.mdi,
        "price_chf": r.resort.day_price_chf,
        "train": _train(r.connection) if r.connection else None,
        "snow_n_rail": {"up_to_pct": offer.up_to_pct, "url": offer.url}
        if offer
        else None,
        "tags": list(r.tags),
        "reasons": {k: round(v, 1) for k, v in r.score.reasons.items()},
    }


def render_table(result: RecommendationResult) -> str:
    """
    Markdown for the dashboard card, one small table per recommendation.

    | classification | score |
    | date | ski resort | weather icon | price |
    | train information | snow and rail |
    """
    shown = [(r, False) for r in result.recommendations]
    if result.outlook:
        shown.append((result.outlook, True))
    if not shown:
        return headline(result)
    return "\n\n---\n\n".join(_block(r, outlook=outlook) for r, outlook in shown)


def _block(r: Recommendation, *, outlook: bool) -> str:
    """Render the three rows of one recommendation."""
    price = r.resort.day_price_chf
    offer = r.resort.snow_n_rail
    train = _train(r.connection)["summary"] if r.connection else "no morning train"
    snow = (
        f"[🎿 Snow'n'Rail up to {offer.up_to_pct} %]({offer.url})"
        if offer
        else NO_VALUE
    )
    label = _classification(r, outlook=outlook)
    return "\n".join(
        [
            f"| **{label}** | **{round(r.score.total)}** | | |",
            "|:--|:--|:-:|--:|",
            f"| {r.day.day:%a %d.%m} | {r.resort.name} ({r.point.name})"
            f" | {r.weather_icon.emoji} | {f'CHF {price:g}' if price else NO_VALUE} |",
            f"| 🚆 {train} | {snow} | | |",
        ]
    )


def _classification(r: Recommendation, *, outlook: bool) -> str:
    """Good day / Not good / Outlook (days 6-7)."""
    if outlook:
        return "Outlook"
    return "Good day" if r.is_good else "Not good"


def _train(c: Connection) -> dict:
    """Departure, platform, arrival, duration and a one-line summary."""
    rides = []
    for i, leg in enumerate(c.legs):
        number = f" ({leg.train_number})" if leg.train_number else ""
        last = i == len(c.legs) - 1
        to = (
            f"{leg.arrival:%H:%M} {leg.arrival_station}"
            if last
            else leg.arrival_station
        )
        rides.append(f"{leg.line}{number} → {to}")
    platform = f" pl. {c.platform}" if c.platform else ""
    summary = f"{c.departure:%H:%M}{platform} {', '.join(rides)} · {c.duration_min} min"
    return {
        "departure": f"{c.departure:%H:%M}",
        "platform": c.platform,
        "arrival": f"{c.arrival:%H:%M}",
        "duration_min": c.duration_min,
        "transfers": c.transfers,
        "summary": summary,
    }
