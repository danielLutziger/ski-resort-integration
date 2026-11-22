"""User settings for the recommendation."""

from dataclasses import dataclass

SATURDAY = 5
SUNDAY = 6


@dataclass(frozen=True, slots=True)
class Settings:
    """Settings for recommendation."""

    allowed_weekdays: frozenset[int] = frozenset({SATURDAY, SUNDAY})
    max_results: int = 3
    # below this score the day is not considered a good day
    min_good_score: float = 60.0
