from pathlib import Path
import yaml
from custom_components.ski_resort_recommender.lib.models import Resort


def load_resorts(file: Path) -> list[Resort]:
    with file.open(encoding="utf-8") as f:
        return [Resort(**entry) for entry in yaml.safe_load(f)]
