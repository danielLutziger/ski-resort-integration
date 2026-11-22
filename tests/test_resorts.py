"""Tests for the resort files (resorts/<key>.yaml) and their loader."""

from pathlib import Path

import pytest

from custom_components.ski_resort_recommender.lib.models import SnowRailOffer
from custom_components.ski_resort_recommender.lib.resorts import (
    MAX_POINTS,
    load_resorts,
)

RESORTS_DIR = (
    Path(__file__).parent.parent
    / "custom_components"
    / "ski_resort_recommender"
    / "resorts"
)


def test_every_resort_has_valid_points() -> None:
    """Points: 1-5 per resort, unique names, plausible Alpine positions."""
    resorts = load_resorts(RESORTS_DIR)

    assert len({r.key for r in resorts}) == len(resorts)
    for resort in resorts:
        assert 1 <= len(resort.points) <= MAX_POINTS, resort.key
        assert len({p.name for p in resort.points}) == len(resort.points), resort.key
        for point in resort.points:
            assert 45.8 <= point.lat <= 47.8, (resort.key, point.name)
            assert 5.9 <= point.lon <= 10.6, (resort.key, point.name)
            assert 1000 <= point.elevation_m <= 4000, (resort.key, point.name)
            assert point.weight > 0, (resort.key, point.name)


def write_resort(tmp_path: Path, points: str, extra: str = "") -> Path:
    """Write test.yaml (one resort) with the given points block; return the folder."""
    tmp_path.mkdir(exist_ok=True)
    (tmp_path / "test.yaml").write_text(
        "name: Test\n"
        "meteoswiss_point_id:\n"
        "station: Chur\n"
        "day_price_chf:\n"
        f"points:{points}\n"
        f"{extra}"
    )
    return tmp_path


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


SNOW_N_RAIL = {  # resorts with an SBB Snow'n'Rail offer 2026/27 (issue #19)
    "flims_laax",
    "flumserberg",
    "andermatt_sedrun_disentis",
    "engelberg",
    "pizol",
    "davos_jakobshorn",
    "melchsee_frutt",
    "scuol",
    "arosa_lenzerheide",
    "adelboden_lenk",
    "grindelwald_wengen",
    "verbier",
    "crans_montana",
}


def test_snow_n_rail_offers_in_the_resort_files() -> None:
    """The resorts with an SBB Snow'n'Rail offer have one, the others none."""
    resorts = {r.key: r for r in load_resorts(RESORTS_DIR)}

    with_offer = {key for key, r in resorts.items() if r.snow_n_rail}

    assert with_offer == SNOW_N_RAIL
    for key in SNOW_N_RAIL:
        offer = resorts[key].snow_n_rail
        assert offer is not None
        assert offer.url.startswith("https://freizeit.sbb.ch/en/stories/snownrail-")
        assert 0 < offer.up_to_pct <= 50


def test_snow_n_rail_is_parsed_and_optional(tmp_path: Path) -> None:
    """snow_n_rail: {offer, up_to_pct} becomes a SnowRailOffer; missing = None."""
    point = "\n  - {name: a, lat: 46.8, lon: 9.3, elevation_m: 2000}"
    (without,) = load_resorts(write_resort(tmp_path / "plain", point))
    (resort,) = load_resorts(
        write_resort(
            tmp_path / "offer",
            point,
            "snow_n_rail:\n  offer: snownrail-pizol\n  up_to_pct: 30\n",
        )
    )

    assert without.snow_n_rail is None
    assert resort.snow_n_rail == SnowRailOffer(offer="snownrail-pizol", up_to_pct=30)
    assert (
        resort.snow_n_rail.url == "https://freizeit.sbb.ch/en/stories/snownrail-pizol"
    )


def test_the_file_name_is_the_resort_key(tmp_path: Path) -> None:
    """Adding a resort = adding <key>.yaml; other files are ignored."""
    point = "\n  - {name: a, lat: 46.8, lon: 9.3, elevation_m: 2000}"
    folder = write_resort(tmp_path, point)
    (folder / "notes.txt").write_text("not a resort")

    (resort,) = load_resorts(folder)

    assert resort.key == "test"


def test_resorts_are_sorted_by_key() -> None:
    """Stable order (the Open-Meteo request matches answers by position)."""
    keys = [r.key for r in load_resorts(RESORTS_DIR)]

    assert keys == sorted(keys)
    assert len(keys) == 23


def test_a_file_with_a_list_is_rejected(tmp_path: Path) -> None:
    """Each file holds exactly one resort (no old-style list)."""
    (tmp_path / "old.yaml").write_text("- name: A\n- name: B\n")

    with pytest.raises(ValueError, match=r"old\.yaml"):
        load_resorts(tmp_path)
