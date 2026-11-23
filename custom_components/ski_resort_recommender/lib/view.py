"""What the sensor shows: headline, one entry per recommendation, the table."""

from dataclasses import asdict
from html import escape
from typing import TYPE_CHECKING

from custom_components.ski_resort_recommender.lib.service import (
    Recommendation,
    RecommendationResult,
    RecommendationStatus,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from custom_components.ski_resort_recommender.lib.models import (
        Connection,
        Drive,
    )
    from custom_components.ski_resort_recommender.lib.service import PointResult
    from custom_components.ski_resort_recommender.lib.settings import Settings

# DayForecast values shown in the details, per point
FORECAST_FIELDS = (
    "sunshine_hours",
    "daylight_hours",
    "fresh_snow_cm",
    "snow_depth_cm",
    "gust_max_kmh",
    "temp_ski_c",
    "visibility_m",
    "recent_rain_mm",
    "snow_after_rain_cm",
    "weather_code",
)

HEADLINES = {
    RecommendationStatus.GOOD_DAY: "Good day",
    RecommendationStatus.NO_GOOD_DAY: "No good day",
    RecommendationStatus.NO_FORECAST: "No forecast yet",
}
NO_DATA = "No data yet"
# full-width line between two results (plain HTML, works without card-mod)
DIVIDER = '<tr><td colspan="5"><hr></td></tr>'
# column widths in px: score | date | Dep./Arr. | station + details (rest) | price
COLUMNS = (
    '<colgroup><col width="104"><col width="64"><col width="32"><col>'
    '<col width="42"></colgroup>'
)
SMALL_FONT = 2  # HTML font size of the secondary text (1-7, 3 = normal)
SNOW_N_RAIL_SHORT = "SnR"  # Snow'n'Rail offer


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


def entry(r: Recommendation, *, outlook: bool | None = None) -> dict:
    """One recommendation as plain values (sensor attribute, JSON friendly)."""
    offer = r.resort.snow_n_rail
    return {
        "classification": _classification(
            r, outlook=r.outlook if outlook is None else outlook
        ),
        "is_good": r.is_good,  # also for an outlook day (the card colours it)
        "score": round(r.score.total),
        "date": r.day.day.isoformat(),
        "day": f"{r.day.day:%a %d.%m}",
        "resort": r.resort.name,
        "point": r.point.name,
        "weather_icon": r.weather_icon.mdi,
        "price_chf": r.resort.day_price_chf,
        "train": _train(r.connection) if r.connection else None,
        "car": _car(r.drive) if r.drive else None,
        "snow_n_rail": {"up_to_pct": offer.up_to_pct, "url": offer.url}
        if offer
        else None,
        "tags": list(r.tags),
        "reasons": {k: round(v, 1) for k, v in r.score.reasons.items()},
    }


def detail(r: Recommendation, measured: Mapping[str, float] | None = None) -> dict:
    """Entry plus everything the expanded row shows: points, forecast, legs."""
    data = entry(r)
    data["points"] = [_point(p) for p in r.points]
    data["snow_stations"] = [
        {
            "code": s.code,
            "name": s.name,
            "elevation_m": s.elevation_m,
            "depth_cm": (measured or {}).get(s.code),
        }
        for s in r.resort.snow_stations
    ]
    if r.connection:
        data["train"]["legs"] = [
            {
                "line": leg.line,
                "train_number": leg.train_number,
                "from": leg.departure_station,
                "departure": f"{leg.departure:%H:%M}",
                "platform": leg.platform,
                "to": leg.arrival_station,
                "arrival": f"{leg.arrival:%H:%M}",
            }
            for leg in r.connection.legs
        ]
    return data


def scoring_info(settings: Settings) -> dict:
    """Weights and thresholds for the legend and the formula."""
    return {
        "min_good_score": settings.min_good_score,
        "ranking_days": settings.ranking_days,
        "outlook_days": settings.outlook_days,
        "weights": asdict(settings.scoring),
    }


def results_payload(
    result: RecommendationResult, settings: Settings, error: str | None = None
) -> dict:
    """Everything the modal of the card needs (sent on request, not as attribute)."""
    return {
        "headline": headline(result),
        "last_error": error,
        "results": [detail(r, result.measured_snow_cm) for r in result.all],
        "scoring": scoring_info(settings),
    }


def _point(p: PointResult) -> dict:
    """One weather point: weight, height, its own score and forecast values."""
    return {
        "name": p.point.name,
        "weight": p.point.weight,
        "elevation_m": p.point.elevation_m,
        "score": round(p.score.total),
        "reasons": {k: round(v, 1) for k, v in p.score.reasons.items()},
        "forecast": {field: getattr(p.day, field) for field in FORECAST_FIELDS},
    }


def render_table(result: RecommendationResult) -> str:
    """
    Compact HTML table for the Markdown card, one block of rows per result.

     52         | Hoch-Ybrig · Spirstock                        |  62.-
     Not good ⛅ | Sat 28.11 | Dep. Zürich HB, 07:15 · S5 · Pl. 3 | [SnR]
                |           | Arr. Hoch-Ybrig, 09:10             |
                |           | Car  Weglosen · 0:58 h · 52 km     |   (car mode)

    Only HTML the Markdown card allows (no CSS): font size, rowspan/colspan,
    column widths. No borders and the SnR badge style come from card-mod.
    """
    shown = [(r, False) for r in result.recommendations]
    if result.outlook:
        shown.append((result.outlook, True))
    if not shown:
        return headline(result)
    blocks = ["\n".join(_rows(r, outlook=outlook)) for r, outlook in shown]
    body = f"\n{DIVIDER}\n".join(blocks)
    return f'<table width="100%">\n{COLUMNS}\n{body}\n</table>'


def _rows(r: Recommendation, *, outlook: bool) -> list[str]:
    """Score/resort/price, then date + travel lines (train Dep./Arr., car)."""
    lines: list[tuple[str, str]] = []
    if r.connection or not r.drive:  # car only: no "No train" line
        lines.extend(_departure_arrival(r.connection))
    if r.drive:
        lines.append((_small("Car"), _small(escape(_car(r.drive)["summary"]))))
    span = len(lines) + 1
    label = escape(_classification(r, outlook=outlook))
    score = (
        f'<td rowspan="{span}" align="center"><font size="5"><b>{round(r.score.total)}'
        f"</b></font><br>{_small(f'{label} {r.weather_icon.emoji}')}</td>"
    )
    resort = (
        f'<td colspan="3"><b>{escape(r.resort.name)}</b> · '
        f"{_small(escape(r.point.name))}</td>"
    )
    side = [_price(r.resort.day_price_chf)]
    if r.resort.snow_n_rail:
        side.append(f"<code>{SNOW_N_RAIL_SHORT}</code>")
    price = (
        f'<td rowspan="{span}" align="right">{"<br>".join(p for p in side if p)}</td>'
    )
    day = _small(f"{r.day.day:%a %d.%m}")
    return [
        f"<tr>{score}{resort}{price}</tr>",
        *(
            f"<tr><td>{day if i == 0 else ''}</td><td>{lbl}</td><td>{txt}</td></tr>"
            for i, (lbl, txt) in enumerate(lines)
        ),
    ]


def _departure_arrival(c: Connection | None) -> tuple[tuple[str, str], ...]:
    """(Dep., station, time · first train · platform), (Arr., station, time)."""
    if c is None:
        return ("", _small("No train")), ("", "")
    first, last = (c.legs[0], c.legs[-1]) if c.legs else (None, None)
    dep = [f"{c.departure:%H:%M}"]
    if first:
        dep.append(first.line.replace(" ", ""))
    if c.platform:
        dep.append(f"Pl. {c.platform}")
    dep_station = f"{first.departure_station}, " if first else ""
    arr_station = f"{last.arrival_station}, " if last else ""
    return (
        (_small("Dep."), _small(escape(f"{dep_station}{' · '.join(dep)}"))),
        (_small("Arr."), _small(escape(f"{arr_station}{c.arrival:%H:%M}"))),
    )


def _price(price: float | None) -> str:
    """Day price, CHF implied: 62.- or 76.50."""
    if not price:
        return ""
    return f"{price:.0f}.-" if price == int(price) else f"{price:.2f}"


def _small(text: str) -> str:
    """Secondary text in SMALL_FONT."""
    return f'<font size="{SMALL_FONT}">{text}</font>'


def _classification(r: Recommendation, *, outlook: bool) -> str:
    """Good day / Not good / Outlook (days 6-7)."""
    if outlook:
        return "Outlook"
    return "Good day" if r.is_good else "Not good"


def _car(d: Drive) -> dict:
    """Drive to the closest access point: where, how long, how far."""
    hours, minutes = divmod(d.duration_min, 60)
    return {
        "access": d.access,
        "duration_min": d.duration_min,
        "distance_km": d.distance_km,
        "summary": f"{d.access} · {hours}:{minutes:02d} h · {d.distance_km:.0f} km",
    }


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
        "from": c.legs[0].departure_station if c.legs else None,
        "to": c.legs[-1].arrival_station if c.legs else None,
        "line": c.legs[0].line if c.legs else None,
    }
