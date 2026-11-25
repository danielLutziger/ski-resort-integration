"""Tests for the resort files (resorts/<key>.yaml) and their loader."""

from datetime import date
from pathlib import Path

import pytest

from custom_components.ski_resort_recommender.lib.models import (
    AccessPoint,
    Season,
    SnowRailOffer,
    SnowStation,
)
from custom_components.ski_resort_recommender.lib.resorts import (
    MAX_ACCESS,
    MAX_POINTS,
    MAX_SNOW_STATIONS,
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


def test_snow_stations_are_parsed_and_optional(tmp_path: Path) -> None:
    """snow_stations: list of {code, name, elevation_m}; missing = none."""
    point = "\n  - {name: a, lat: 46.8, lon: 9.3, elevation_m: 2000}"
    (without,) = load_resorts(write_resort(tmp_path / "plain", point))
    (resort,) = load_resorts(
        write_resort(
            tmp_path / "stations",
            point,
            "snow_stations:\n  - {code: CMA2, name: La Fuorcla, elevation_m: 2325}\n",
        )
    )

    assert without.snow_stations == ()
    assert resort.snow_stations == (SnowStation("CMA2", "La Fuorcla", 2325),)


def test_duplicate_snow_stations_are_rejected(tmp_path: Path) -> None:
    """The same station twice would weigh double in the mean."""
    point = "\n  - {name: a, lat: 46.8, lon: 9.3, elevation_m: 2000}"
    station = "  - {code: CMA2, name: La Fuorcla, elevation_m: 2325}\n"
    folder = write_resort(tmp_path, point, "snow_stations:\n" + station * 2)

    with pytest.raises(ValueError, match="snow stations"):
        load_resorts(folder)


def test_resort_files_list_at_most_three_unique_snow_stations() -> None:
    """Station codes are upper case IMIS codes (e.g. CMA2), one request each."""
    for resort in load_resorts(RESORTS_DIR):
        codes = [s.code for s in resort.snow_stations]
        assert len(codes) <= MAX_SNOW_STATIONS, resort.key
        assert all(code.isupper() and code[-1].isdigit() for code in codes)


def test_access_points_are_parsed_and_unique(tmp_path: Path) -> None:
    """access: list of {name, lat, lon}; duplicate names are rejected."""
    point = "\n  - {name: a, lat: 46.8, lon: 9.3, elevation_m: 2000}"
    flims = "  - {name: Flims, lat: 46.8345, lon: 9.2823}\n"
    (resort,) = load_resorts(write_resort(tmp_path / "ok", point, "access:\n" + flims))

    assert resort.access == (AccessPoint("Flims", 46.8345, 9.2823),)
    with pytest.raises(ValueError, match="access points"):
        load_resorts(write_resort(tmp_path / "twice", point, "access:\n" + flims * 2))


def test_every_resort_file_has_access_points() -> None:
    """Drive times need at least one access point per resort."""
    for resort in load_resorts(RESORTS_DIR):
        assert 1 <= len(resort.access) <= MAX_ACCESS, resort.key


def test_car_parks_are_parsed_with_their_walk_to_the_gondola(tmp_path: Path) -> None:
    """parking: list per access point; spaces/price optional; walk computed."""
    point = "\n  - {name: a, lat: 46.8, lon: 9.3, elevation_m: 2000}"
    access = (
        "access:\n"
        "  - name: Flims\n    lat: 46.8345\n    lon: 9.2823\n    parking:\n"
        "      - {name: Stenna, lat: 46.83295, lon: 9.28185, spaces: 1147, "
        "price_chf: 13.6}\n"
        "      - {name: Other, lat: 46.8345, lon: 9.2823}\n"
    )
    (resort,) = load_resorts(write_resort(tmp_path, point, access))

    stenna, other = resort.access[0].parking
    assert (stenna.name, stenna.spaces, stenna.price_chf) == ("Stenna", 1147, 13.6)
    assert stenna.walk_m == pytest.approx(178, abs=2)
    assert (other.spaces, other.price_chf, other.walk_m) == (None, None, 0)


def test_access_points_are_valley_stations_with_parking() -> None:
    """Every access point has a car park; none is a mountain station."""
    for resort in load_resorts(RESORTS_DIR):
        for point in resort.access:
            assert point.parking, (resort.key, point.name)
            assert all(c.walk_m < 1000 for c in point.parking), point.name


def test_season_and_point_dates_are_parsed(tmp_path: Path) -> None:
    """season: dates from the YAML file; a point can open later."""
    point = "\n  - {name: a, lat: 46.8, lon: 9.3, elevation_m: 2000, opens: 2026-12-19}"
    season = "season: {start: 2026-11-28, end: 2027-04-04, daily_from: 2026-12-05}\n"
    (resort,) = load_resorts(write_resort(tmp_path, point, season))

    assert resort.season == Season(
        start=date(2026, 11, 28), end=date(2027, 4, 4), daily_from=date(2026, 12, 5)
    )
    assert resort.points[0].opens == date(2026, 12, 19)


def test_season_dates_must_be_in_order(tmp_path: Path) -> None:
    """A typo (end before start) would hide a resort silently."""
    point = "\n  - {name: a, lat: 46.8, lon: 9.3, elevation_m: 2000}"
    season = "season: {start: 2026-11-28, end: 2026-04-04}\n"

    with pytest.raises(ValueError, match="season"):
        load_resorts(write_resort(tmp_path, point, season))


def test_every_resort_file_has_a_season_with_plausible_dates() -> None:
    """Every resort has dates; points open inside the season."""
    for resort in load_resorts(RESORTS_DIR):
        season = resort.season
        assert season is not None, resort.key
        for point in resort.points:
            if point.opens:
                assert season.start <= point.opens <= season.end, (resort.key, point)
