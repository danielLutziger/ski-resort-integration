"""Pick the best resort/day combinations."""

from collections import defaultdict
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from enum import StrEnum
from statistics import median
from typing import TYPE_CHECKING

from custom_components.ski_resort_recommender.lib.models import (
    Connection,
    DayForecast,
    Drive,
    Forecasts,
    Resort,
    WeatherPoint,
)
from custom_components.ski_resort_recommender.lib.scoring import (
    DayScore,
    combine_scores,
    is_no_go,
    score_day,
    with_reason,
)
from custom_components.ski_resort_recommender.lib.settings import Settings
from custom_components.ski_resort_recommender.lib.weather_codes import (
    WeatherIcon,
    weather_icon,
)

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass(frozen=True, slots=True)
class PointResult:
    """Forecast and score of one weather point of a resort-day (for the details)."""

    point: WeatherPoint
    day: DayForecast
    score: DayScore


@dataclass(frozen=True, slots=True)
class Recommendation:
    """One resort on one day: combined score, shown with its best point."""

    resort: Resort
    day: DayForecast  # forecast of the best point
    score: DayScore  # weighted average over the resort's points
    is_good: bool
    point: WeatherPoint  # best point of the resort on that day
    connection: Connection | None = None  # morning train, None = none found
    drive: Drive | None = None  # car to the closest access point (car mode)
    tags: tuple[str, ...] = ()  # e.g. SNOW_N_RAIL_TAG
    weather_icon: WeatherIcon = WeatherIcon.UNKNOWN  # over all points and ski hours
    points: tuple[PointResult, ...] = ()  # every point of the resort that day
    outlook: bool = False  # day after the ranking window (days 6-7)
    closed: bool = False  # not open that day (season): listed, never recommended


# resort has an SBB Snow'n'Rail offer (per-day availability: issue #19)
SNOW_N_RAIL_TAG = "snow-n-rail"


class RecommendationStatus(StrEnum):
    """Headline state of a result."""

    GOOD_DAY = "good_day"
    NO_GOOD_DAY = "no_good_day"
    NO_FORECAST = "no_forecast"
    ALL_CLOSED = "all_closed"


@dataclass(frozen=True, slots=True)
class RecommendationResult:
    """Class object that we visualize in HA."""

    recommendations: tuple[Recommendation, ...]  # ranked days, best first
    outlook: Recommendation | None = None  # best day after the ranking window
    all: tuple[
        Recommendation, ...
    ] = ()  # every resort-day up to outlook_days, best first, closed ones last
    # measured snow depth (cm) per SLF station code, as used for the base
    measured_snow_cm: dict[str, float] = field(default_factory=dict)

    @property
    def has_good_day(self) -> bool:
        """Check whether the day is over a threshold."""
        return any(r.is_good for r in self.recommendations)

    @property
    def status(self) -> RecommendationStatus:
        """Return the headline: good day, no good day, or no forecast at all."""
        if not self.recommendations:
            if any(r.closed for r in self.all):
                return RecommendationStatus.ALL_CLOSED
            return RecommendationStatus.NO_FORECAST
        if self.has_good_day:
            return RecommendationStatus.GOOD_DAY
        return RecommendationStatus.NO_GOOD_DAY


def pick_recommendations(  # noqa: PLR0913 (optional keyword-only inputs)
    resorts: list[Resort],
    forecasts: Forecasts,
    settings: Settings | None = None,
    *,
    today: date | None = None,
    travel: dict[str, Connection] | None = None,
    prices: dict[str, float] | None = None,
    drives: dict[str, Drive] | None = None,
) -> RecommendationResult:
    """
    Score all allowed future days; rank days 1..ranking_days, outlook after.

    travel: one morning connection per resort key (reference day); its duration
    gives the relative travel points. Without it travel scores 0 everywhere.
    drives: drive to the closest access point per resort key (car mode). With
    train and car, the faster of the two counts for the travel points.
    prices: day ticket price per resort key (e.g. live prices); default is
    Resort.day_price_chf from the resort files. Cheaper for its size (piste km) =
    more price points.
    """
    ranked: list[Recommendation] = []
    outlook: list[Recommendation] = []
    closed: list[Recommendation] = []
    settings = settings or Settings()
    today = today or date.today()  # noqa: DTZ011
    ranking_end = today + timedelta(days=settings.ranking_days)
    outlook_end = today + timedelta(days=settings.outlook_days)
    travel = travel or {}
    drives = drives or {}
    minutes = {key: c.duration_min for key, c in travel.items()}
    for key, drive in drives.items():
        minutes[key] = min(minutes.get(key, drive.duration_min), drive.duration_min)
    travel_points = _relative_points(minutes, settings.scoring.travel_points)
    if prices is None:
        prices = {r.key: r.day_price_chf for r in resorts if r.day_price_chf}
    price_points = _relative_points(
        _prices_at_typical_size(resorts, prices, settings.scoring.price_size_exponent),
        settings.scoring.price_points,
    )

    for resort in resorts:
        point_days: dict[date, list[tuple[WeatherPoint, DayForecast]]] = defaultdict(
            list
        )
        for point in resort.points:
            for day in forecasts.get(resort.key, {}).get(point.name, []):
                if not today < day.day <= outlook_end:  # not today, not the past
                    continue
                if day.day.weekday() not in settings.allowed_weekdays:
                    continue
                if not day.has_data:
                    continue
                point_days[day.day].append((point, day))
        for day, points in point_days.items():
            in_outlook = day > ranking_end
            is_open = resort.is_open(day)
            if is_open:  # sectors that open later do not count
                points = [(p, d) for p, d in points if p.is_open(day)]  # noqa: PLW2901
                if not points:  # the open sectors have no forecast
                    continue
            target = (outlook if in_outlook else ranked) if is_open else closed
            extras = {
                "travel": travel_points.get(resort.key, 0.0),
                "price": price_points.get(resort.key, 0.0),
            }
            recommendation = _recommend(resort, points, settings, extras)
            tags = (SNOW_N_RAIL_TAG,) if resort.snow_n_rail else ()
            target.append(
                replace(
                    recommendation,
                    connection=travel.get(resort.key),
                    drive=drives.get(resort.key),
                    tags=tags,
                    outlook=in_outlook,
                    closed=not is_open,
                    is_good=recommendation.is_good and is_open,
                )
            )
    ranked.sort(key=lambda r: r.score.total, reverse=True)
    everything = sorted([*ranked, *outlook], key=lambda r: r.score.total, reverse=True)
    everything += sorted(closed, key=lambda r: r.score.total, reverse=True)
    return RecommendationResult(
        tuple(ranked[: settings.max_results]),
        outlook=max(outlook, key=lambda r: r.score.total, default=None)
        if settings.show_outlook
        else None,
        all=tuple(everything),
    )


def _recommend(
    resort: Resort,
    points: list[tuple[WeatherPoint, DayForecast]],
    settings: Settings,
    extras: dict[str, float],
) -> Recommendation:
    """Combine the point scores of one resort-day, add travel/price, judge it."""
    scored = [(point, day, score_day(day, settings.scoring)) for point, day in points]
    score = combine_scores([(point.weight, s) for point, _, s in scored])
    for name, extra in extras.items():
        score = with_reason(score, name, extra)
    best_point, best_day, _ = max(scored, key=lambda item: item[2].total)
    # NO_GO only counts at the best point: a shower at one side area is fine
    is_good = score.total >= settings.min_good_score and not is_no_go(
        best_day, settings.scoring
    )
    icon = weather_icon(
        [
            (point.weight, day.weather_codes_ski or _daily_code(day))
            for point, day in points
        ],
        sun_share=_sun_share(points),
    )
    return Recommendation(
        resort=resort,
        day=best_day,
        score=score,
        is_good=is_good,
        point=best_point,
        weather_icon=icon,
        points=tuple(PointResult(point, day, s) for point, day, s in scored),
    )


def _daily_code(day: DayForecast) -> tuple[int, ...]:
    """Fallback without hourly codes: the daily code (if any)."""
    return () if day.weather_code is None else (day.weather_code,)


def _prices_at_typical_size(
    resorts: list[Resort], prices: dict[str, float], exponent: float
) -> dict[str, float]:
    """Return what every ticket would cost at the typical (median) piste km."""
    sizes = {r.key: r.piste_km for r in resorts if r.piste_km and r.key in prices}
    if not sizes:
        return prices
    typical = median(sizes.values())
    return {
        key: price * (typical / sizes.get(key, typical)) ** exponent
        for key, price in prices.items()
    }


def _relative_points(values: dict[str, float], points: float) -> dict[str, float]:
    """Lower is better: the lowest value gets all points, the highest 0, linear."""
    if not values:
        return {}
    lowest, highest = min(values.values()), max(values.values())
    if lowest == highest:
        return dict.fromkeys(values, points)
    return {
        key: (highest - value) / (highest - lowest) * points
        for key, value in values.items()
    }


def attach_connections(
    result: RecommendationResult, connections: dict[tuple[str, date], Connection]
) -> RecommendationResult:
    """Show the connection of the recommended day (keyed by resort key and day)."""

    def attach(r: Recommendation) -> Recommendation:
        found = connections.get((r.resort.key, r.day.day))
        return replace(r, connection=found) if found else r

    return _each(result, attach)


def attach_routes(
    result: RecommendationResult, routes: dict[str, tuple[tuple[float, float], ...]]
) -> RecommendationResult:
    """Add the road geometry (map) to the drive of every result of a resort."""

    def attach(r: Recommendation) -> Recommendation:
        route = routes.get(r.resort.key)
        if not route or not r.drive:
            return r
        return replace(r, drive=replace(r.drive, route=route))

    return _each(result, attach)


def _each(
    result: RecommendationResult, change: Callable[[Recommendation], Recommendation]
) -> RecommendationResult:
    """Apply change to every recommendation; replace keeps the other fields."""
    return replace(
        result,
        recommendations=tuple(change(r) for r in result.recommendations),
        outlook=change(result.outlook) if result.outlook else None,
        all=tuple(change(r) for r in result.all),
    )


def _sun_share(points: list[tuple[WeatherPoint, DayForecast]]) -> float | None:
    """Weighted sunshine / daylight over the points (None without data)."""
    shares = [
        (point.weight, min(day.sunshine_hours / day.daylight_hours, 1.0))
        for point, day in points
        if day.sunshine_hours is not None and day.daylight_hours
    ]
    if not shares:
        return None
    return sum(w * share for w, share in shares) / sum(w for w, _ in shares)
