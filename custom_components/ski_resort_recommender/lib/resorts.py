"""Load the resort list from resorts.yaml."""

from typing import TYPE_CHECKING

import yaml

from custom_components.ski_resort_recommender.lib.models import (
    Resort,
    SnowRailOffer,
    WeatherPoint,
)

if TYPE_CHECKING:
    from pathlib import Path

MAX_POINTS = 5  # every point is one location in each Open-Meteo request


def load_resorts(file: Path) -> list[Resort]:
    """Read the YAML file and return one Resort per entry."""
    with file.open(encoding="utf-8") as f:
        return [_resort(entry) for entry in yaml.safe_load(f)]


def _resort(entry: dict) -> Resort:
    """Build one Resort and check its points."""
    points = tuple(WeatherPoint(**point) for point in entry.pop("points"))
    names = [p.name for p in points]
    if not 1 <= len(points) <= MAX_POINTS or len(set(names)) != len(names):
        msg = f"{entry['key']}: needs 1-{MAX_POINTS} points with unique names"
        raise ValueError(msg)
    offer = entry.pop("snow_n_rail", None)
    snow_n_rail = SnowRailOffer(**offer) if offer else None
    return Resort(**entry, points=points, snow_n_rail=snow_n_rail)
