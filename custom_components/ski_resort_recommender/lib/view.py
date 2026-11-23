"""What the sensor shows: headline, one entry per recommendation, the table."""

from html import escape
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
NO_DATA = "No data yet"
SCORE_COLUMN_PX = 64  # left column: big score, small classification + icon
SNOW_N_RAIL_SHORT = "SaR"  # Snow'n'Rail offer


def headline(result: RecommendationResult) -> str:
    """Sensor state: Good day / No good day / No forecast yet."""
    return HEADLINES[result.status]


def sensor_state(result: RecommendationResult | None) -> str:
    """Headline, or "No data yet" before the first successful update."""
    return NO_DATA if result is None else headline(result)


def sensor_table(result: RecommendationResult | None, error: str | None) -> str:
    """Table for the card; explains a missing or outdated result."""
    if result is None:
        return f"⚠️ {NO_DATA}: {error}" if error else f"⚠️ {NO_DATA}"
    table = render_table(result)
    if error:
        table += f"\n\n⚠️ Last update failed: {error}. Showing the last result."
    return table


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
    Compact HTML table for the Markdown card, two rows per result.

    52          | Hoch-Ybrig · Sat 28.11
    Not good ☁️ | 07:15 · S5 · Pl. 3 · Arr. 09:15 · SaR · 62.-

    Only HTML the Markdown card allows (no CSS): font size and column width.
    Borders, padding and "…" for long text come from card-mod (README).
    """
    shown = [(r, False) for r in result.recommendations]
    if result.outlook:
        shown.append((result.outlook, True))
    if not shown:
        return headline(result)
    rows = [row for r, outlook in shown for row in _rows(r, outlook=outlook)]
    return "\n".join(["<table>", *rows, "</table>"])


def _rows(r: Recommendation, *, outlook: bool) -> list[str]:
    """Score | resort · day, then classification + icon | compact details."""
    left = f'<td width="{SCORE_COLUMN_PX}">'
    label = escape(_classification(r, outlook=outlook))
    return [
        f'<tr>{left}<font size="5"><b>{round(r.score.total)}</b></font></td>'
        f"<td><b>{escape(r.resort.name)}</b> · {r.day.day:%a %d.%m}</td></tr>",
        f'<tr>{left}<font size="1">{label}</font> {r.weather_icon.emoji}</td>'
        f"<td>{escape(_details(r))}</td></tr>",
    ]


def _details(r: Recommendation) -> str:
    """Departure · first train · platform · arrival · SaR · price (CHF implied)."""
    parts = [_compact_train(r.connection) if r.connection else "No train"]
    if r.resort.snow_n_rail:
        parts.append(SNOW_N_RAIL_SHORT)
    if price := r.resort.day_price_chf:
        parts.append(f"{price:.0f}.-" if price == int(price) else f"{price:.2f}")
    return " · ".join(parts)


def _compact_train(c: Connection) -> str:
    """07:15 · S5 · Pl. 3 · Arr. 09:15 (the train you board at home)."""
    parts = [f"{c.departure:%H:%M}"]
    if c.legs:
        parts.append(c.legs[0].line.replace(" ", ""))
    if c.platform:
        parts.append(f"Pl. {c.platform}")
    parts.append(f"Arr. {c.arrival:%H:%M}")
    return " · ".join(parts)


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
