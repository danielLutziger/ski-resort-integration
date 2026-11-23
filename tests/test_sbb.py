"""Tests for the SBB connection parsing and the choice of the morning connection."""

import asyncio
import json
from dataclasses import replace
from datetime import date, time
from pathlib import Path

import pytest

from custom_components.ski_resort_recommender.lib.errors import SkiApiConnectionError
from custom_components.ski_resort_recommender.lib.sbb import (
    _leg,
    _parse,
    _pick,
    find_stations,
)
from custom_components.ski_resort_recommender.lib.settings import Settings
from tests.fakes import FakeResponse, FakeSession

FIXTURE = Path(__file__).parent / "fixtures" / "sbb_connections.json"
SATURDAY = date(2026, 11, 28)
# arrival window around lift opening, written out (tests never rely on defaults)
SETTINGS = Settings(
    home_station="Zürich HB",
    departure_earliest=time(5, 0),
    arrival_target=time(9, 0),
    arrival_earliest=time(8, 45),
    arrival_latest=time(9, 30),
)


def connections() -> list:
    """Parse the saved Zürich HB -> Flims Dorf, Bergbahnen response (Sat 28.11)."""
    return _parse(json.loads(FIXTURE.read_text()))


def test_parse_reads_times_platform_and_legs() -> None:
    """Departure, platform, arrival, duration, transfers and the train legs."""
    last = connections()[-1]

    assert f"{last.departure:%H:%M}" == "07:07"
    assert last.platform == "9"
    assert f"{last.arrival:%H:%M}" == "09:01"
    assert last.duration_min == 114
    assert last.transfers == 1
    train, bus = last.legs
    assert (train.line, train.train_number) == ("IC 3", "1057")
    assert (train.departure_station, train.arrival_station) == ("Zürich HB", "Chur")
    assert train.platform == "9"
    # buses have internal trip ids instead of train numbers: not shown
    assert (bus.line, bus.train_number) == ("B 81", None)
    assert bus.arrival_station == "Flims Dorf, Bergbahnen"


def test_pick_takes_the_arrival_closest_to_the_target_in_the_window() -> None:
    """08:45-09:30, target 09:00: the 07:07 train arriving 09:01."""
    chosen = _pick(connections(), SATURDAY, SETTINGS)

    assert chosen is not None
    assert f"{chosen.departure:%H:%M}" == "07:07"


def test_pick_without_a_connection_in_the_window_returns_none() -> None:
    """No guessing: outside the window there is no morning connection."""
    late = replace(
        SETTINGS,
        arrival_target=time(11, 0),
        arrival_earliest=time(10, 45),
        arrival_latest=time(11, 30),
    )

    assert _pick(connections(), SATURDAY, late) is None


def test_pick_ignores_connections_that_leave_the_day_before() -> None:
    """An overnight trip from the evening before is not a morning connection."""
    assert _pick(connections(), date(2026, 11, 29), SETTINGS) is None


def test_pick_ignores_night_trips_before_departure_earliest() -> None:
    """A 01:05 night bus that arrives in the window is not a morning connection."""
    early = replace(
        SETTINGS,
        arrival_target=time(6, 30),
        arrival_earliest=time(6, 0),
        arrival_latest=time(7, 30),
    )
    no_limit = replace(early, departure_earliest=time(0, 0))

    with_limit = _pick(connections(), SATURDAY, early)
    without_limit = _pick(connections(), SATURDAY, no_limit)

    assert without_limit is not None
    assert f"{without_limit.departure:%H:%M}" == "01:05"  # arrives 06:31
    assert with_limit is None  # 04:18 -> 07:01 also leaves before 05:00


def test_leg_without_category_has_no_none_in_its_line() -> None:
    """Some lifts (e.g. Unterterzen-Flumserberg gondola) come without a category."""
    section = json.loads(FIXTURE.read_text())["connections"][-1]["sections"][0]
    section["journey"] = {**section["journey"], "category": None, "number": "2790"}

    leg = _leg(section)

    assert leg.line == "2790"
    assert leg.train_number is None  # not a known train category


def test_find_stations_returns_the_station_names() -> None:
    """The SBB station search gives the names in API order."""
    payload = {"stations": [{"name": "Zürich HB"}, {"name": "Zürich Oerlikon"}]}
    session = FakeSession(lambda _url, _params: FakeResponse(payload))

    names = asyncio.run(find_stations(session, "Zürich"))

    assert names == ["Zürich HB", "Zürich Oerlikon"]
    assert session.calls == [{"query": "Zürich", "type": "station"}]


def test_find_stations_network_error_is_a_connection_error() -> None:
    """The options form shows "cannot connect" instead of crashing."""
    session = FakeSession(lambda _url, _params: FakeResponse(status=503))

    with pytest.raises(SkiApiConnectionError):
        asyncio.run(find_stations(session, "Zürich"))


def test_leg_stops_come_from_the_pass_list_else_departure_and_arrival() -> None:
    """(lat, lon) of every stop (x = lat, y = lon); without a list the two ends."""
    section = json.loads(FIXTURE.read_text())["connections"][0]["sections"][0]
    stop = {"station": {"name": "Sargans", "coordinate": {"x": 47.04, "y": 9.44}}}
    with_list = {**section, "journey": {**section["journey"], "passList": [stop] * 2}}
    ends = {
        **section,
        "departure": {
            **section["departure"],
            "station": {"name": "A", "coordinate": {"x": 47.3, "y": 8.5}},
        },
        "arrival": {
            **section["arrival"],
            "station": {"name": "B", "coordinate": {"x": 47.0, "y": 9.4}},
        },
    }

    assert _leg(with_list).stops == ((47.04, 9.44), (47.04, 9.44))
    assert _leg(ends).stops == ((47.3, 8.5), (47.0, 9.4))
