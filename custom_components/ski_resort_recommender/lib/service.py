from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from custom_components.ski_resort_recommender.lib.models import DayForecast, Resort
from custom_components.ski_resort_recommender.lib.scoring import DayScore, score_day
from custom_components.ski_resort_recommender.lib.settings import Settings
from custom_components.ski_resort_recommender.lib.weather_codes import (
    WeatherClass,
    classify,
)


@dataclass(frozen=True, slots=True)
class Recommendation:
    """Recommendation for the ski resorts."""

    resort: Resort
    day: DayForecast
    score: DayScore
    is_good: bool


class RecommendationStatus(StrEnum):
    """Headline state of a result."""

    GOOD_DAY = "good_day"
    NO_GOOD_DAY = "no_good_day"
    NO_FORECAST = "no_forecast"


@dataclass(frozen=True, slots=True)
class RecommendationResult:
    """Class object that we visualize in HA."""

    recommendations: tuple[Recommendation, ...]

    @property
    def has_good_day(self) -> bool:
        """Check whether the day is over a threshold."""
        return any(r.is_good for r in self.recommendations)

    @property
    def status(self) -> RecommendationStatus:
        """Return the headline: good day, scored but no good day, or no forecast at all."""
        if not self.recommendations:
            return RecommendationStatus.NO_FORECAST
        if self.has_good_day:
            return RecommendationStatus.GOOD_DAY
        return RecommendationStatus.NO_GOOD_DAY


def pick_recommendations(
    resorts: list[Resort],
    forecasts: dict[str, list[DayForecast]],
    settings: Settings | None,
    *,
    today: date | None,
) -> RecommendationResult:
    candidates: list[Recommendation] = []
    settings = settings or Settings()
    today = today or date.today()  # noqa: DTZ011

    for resort in resorts:
        for day in forecasts.get(resort.key, []):
            if day.day <= today:  # not today, not the past
                continue
            if day.day.weekday() not in settings.allowed_weekdays:
                continue
            if not day.has_data:
                continue
            score = score_day(day)
            is_good = (
                score.total >= settings.min_good_score
                and classify(day.weather_code) is not WeatherClass.NO_GO
            )
            candidates.append(
                Recommendation(resort=resort, day=day, score=score, is_good=is_good)
            )
    candidates.sort(key=lambda r: r.score.total, reverse=True)
    return RecommendationResult(tuple(candidates[: settings.max_results]))
