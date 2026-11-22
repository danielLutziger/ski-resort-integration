"""Pick the best resort/day combinations."""

from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import date, timedelta
from enum import StrEnum

from custom_components.ski_resort_recommender.lib.models import (
    Connection,
    DayForecast,
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


@dataclass(frozen=True, slots=True)
class Recommendation:
    """One resort on one day: combined score, shown with its best point."""

    resort: Resort
    day: DayForecast  # forecast of the best point
    score: DayScore  # weighted average over the resort's points
    is_good: bool
    point: WeatherPoint  # best point of the resort on that day
    connection: Connection | None = None  # morning train, None = none found


class RecommendationStatus(StrEnum):
    """Headline state of a result."""

    GOOD_DAY = "good_day"
    NO_GOOD_DAY = "no_good_day"
    NO_FORECAST = "no_forecast"


@dataclass(frozen=True, slots=True)
class RecommendationResult:
    """Class object that we visualize in HA."""

    recommendations: tuple[Recommendation, ...]  # ranked days, best first
    outlook: Recommendation | None = None  # best day after the ranking window

    @property
    def has_good_day(self) -> bool:
        """Check whether the day is over a threshold."""
        return any(r.is_good for r in self.recommendations)

    @property
    def status(self) -> RecommendationStatus:
        """Return the headline: good day, no good day, or no forecast at all."""
        if not self.recommendations:
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
) -> RecommendationResult:
    """
    Score all allowed future days; rank days 1..ranking_days, outlook after.

    travel: one morning connection per resort key (reference day); its duration
    gives the relative travel points. Without it travel scores 0 everywhere.
    prices: day ticket price per resort key (e.g. live prices); default is
    Resort.day_price_chf from resorts.yaml. Cheaper = more price points.
    """
    ranked: list[Recommendation] = []
    outlook: list[Recommendation] = []
    settings = settings or Settings()
    today = today or date.today()  # noqa: DTZ011
    ranking_end = today + timedelta(days=settings.ranking_days)
    outlook_end = today + timedelta(days=settings.outlook_days)
    travel = travel or {}
    travel_points = _relative_points(
        {key: c.duration_min for key, c in travel.items()},
        settings.scoring.travel_points,
    )
    if prices is None:
        prices = {r.key: r.day_price_chf for r in resorts if r.day_price_chf}
    price_points = _relative_points(prices, settings.scoring.price_points)

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
            target = ranked if day <= ranking_end else outlook
            extras = {
                "travel": travel_points.get(resort.key, 0.0),
                "price": price_points.get(resort.key, 0.0),
            }
            recommendation = _recommend(resort, points, settings, extras)
            target.append(replace(recommendation, connection=travel.get(resort.key)))
    ranked.sort(key=lambda r: r.score.total, reverse=True)
    return RecommendationResult(
        tuple(ranked[: settings.max_results]),
        outlook=max(outlook, key=lambda r: r.score.total, default=None),
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
    return Recommendation(
        resort=resort, day=best_day, score=score, is_good=is_good, point=best_point
    )


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

    return RecommendationResult(
        tuple(attach(r) for r in result.recommendations),
        outlook=attach(result.outlook) if result.outlook else None,
    )
