"""Load the resort list from resorts.yaml."""

from typing import TYPE_CHECKING

import yaml

from custom_components.ski_resort_recommender.lib.models import Resort

if TYPE_CHECKING:
    from pathlib import Path


def load_resorts(file: Path) -> list[Resort]:
    """Read the YAML file and return one Resort per entry."""
    with file.open(encoding="utf-8") as f:
        return [Resort(**entry) for entry in yaml.safe_load(f)]
