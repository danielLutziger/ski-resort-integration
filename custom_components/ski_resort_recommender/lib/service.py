"""Pick the best resort/day combinations."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum

from custom_components.ski_resort_recommender.lib.models import (
    DayForecast,
    Forecasts,
    Resort,
    WeatherPoint,
)
from custom_components.ski_resort_recommender.lib.scoring import (
    DayScore,
    combine_scores,
    score_day,
)
from custom_components.ski_resort_recommender.lib.settings import Settings
from custom_components.ski_resort_recommender.lib.weather_codes import (
    WeatherClass,
    classify,
)


@dataclass(frozen=True, slots=True)
class Recommendation:
    """One resort on one day: combined score, shown with its best point."""

    resort: Resort
    day: DayForecast  # forecast of the best point
    score: DayScore  # weighted average over the resort's points
    is_good: bool
    point: WeatherPoint  # best point of the resort on that day


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


def pick_recommendations(
    resorts: list[Resort],
    forecasts: Forecasts,
    settings: Settings | None = None,
    *,
    today: date | None = None,
) -> RecommendationResult:
    """Score all allowed future days; rank days 1..ranking_days, outlook after."""
    ranked: list[Recommendation] = []
    outlook: list[Recommendation] = []
    settings = settings or Settings()
    today = today or date.today()  # noqa: DTZ011
    ranking_end = today + timedelta(days=settings.ranking_days)
    outlook_end = today + timedelta(days=settings.outlook_days)

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
            target.append(_recommend(resort, points, settings))
    ranked.sort(key=lambda r: r.score.total, reverse=True)
    return RecommendationResult(
        tuple(ranked[: settings.max_results]),
        outlook=max(outlook, key=lambda r: r.score.total, default=None),
    )


def _recommend(
    resort: Resort,
    points: list[tuple[WeatherPoint, DayForecast]],
    settings: Settings,
) -> Recommendation:
    """Combine the point scores of one resort-day into one recommendation."""
    scored = [(point, day, score_day(day, settings.scoring)) for point, day in points]
    score = combine_scores([(point.weight, s) for point, _, s in scored])
    best_point, best_day, _ = max(scored, key=lambda item: item[2].total)
    # NO_GO only counts at the best point: a shower at one side area is fine
    is_good = (
        score.total >= settings.min_good_score
        and classify(best_day.weather_code) is not WeatherClass.NO_GO
    )
    return Recommendation(
        resort=resort, day=best_day, score=score, is_good=is_good, point=best_point
    )
