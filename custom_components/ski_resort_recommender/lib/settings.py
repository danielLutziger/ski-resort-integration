from dataclasses import dataclass

SATURDAY = 5
SUNDAY = 6


@dataclass
class Settings:
    """Settings for recommendation."""

    allowed_weekdays: frozenset[int] = frozenset({0, 1, 2, 3, 4, SATURDAY, SUNDAY})
    max_results: int = 200
    min_good_score: float = (
        60.0  # below this score the day is not considere da good day
    )
