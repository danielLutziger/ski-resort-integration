"""Tests for resorts.yaml and its loader."""

from pathlib import Path

import pytest

from custom_components.ski_resort_recommender.lib.resorts import (
    MAX_POINTS,
    load_resorts,
)

RESORTS_FILE = (
    Path(__file__).parent.parent
    / "custom_components"
    / "ski_resort_recommender"
    / "resorts.yaml"
)


def test_every_resort_has_valid_points() -> None:
    """Points: 1-5 per resort, unique names, plausible Alpine positions."""
    resorts = load_resorts(RESORTS_FILE)

    assert len({r.key for r in resorts}) == len(resorts)
    for resort in resorts:
        assert 1 <= len(resort.points) <= MAX_POINTS, resort.key
        assert len({p.name for p in resort.points}) == len(resort.points), resort.key
        for point in resort.points:
            assert 45.8 <= point.lat <= 47.8, (resort.key, point.name)
            assert 5.9 <= point.lon <= 10.6, (resort.key, point.name)
            assert 1000 <= point.elevation_m <= 4000, (resort.key, point.name)
            assert point.weight > 0, (resort.key, point.name)


def write_resort(tmp_path: Path, points: str) -> Path:
    """Write a one-resort YAML file with the given points block."""
    file = tmp_path / "resorts.yaml"
    file.write_text(
        "- key: test\n"
        "  name: Test\n"
        "  meteoswiss_point_id:\n"
        "  station: Chur\n"
        "  day_price_chf:\n"
        f"  points:{points}\n"
    )
    return file


def test_weight_defaults_to_one(tmp_path: Path) -> None:
    """A point without weight counts once."""
    file = write_resort(
        tmp_path, "\n    - {name: a, lat: 46.8, lon: 9.3, elevation_m: 2000}"
    )

    (resort,) = load_resorts(file)

    assert resort.points[0].weight == 1


def test_resort_without_points_is_rejected(tmp_path: Path) -> None:
    """Every resort needs at least one point."""
    file = write_resort(tmp_path, " []")

    with pytest.raises(ValueError, match="test"):
        load_resorts(file)


def test_too_many_points_are_rejected(tmp_path: Path) -> None:
    """At most MAX_POINTS points per resort (one request location each)."""
    points = "".join(
        f"\n    - {{name: p{i}, lat: 46.8, lon: 9.3, elevation_m: 2000}}"
        for i in range(MAX_POINTS + 1)
    )
    file = write_resort(tmp_path, points)

    with pytest.raises(ValueError, match="test"):
        load_resorts(file)


def test_duplicate_point_names_are_rejected(tmp_path: Path) -> None:
    """Point names are keys in the forecasts, so they must be unique."""
    point = "\n    - {name: a, lat: 46.8, lon: 9.3, elevation_m: 2000}"
    file = write_resort(tmp_path, point * 2)

    with pytest.raises(ValueError, match="test"):
        load_resorts(file)
