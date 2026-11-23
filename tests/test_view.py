"""Tests for the sensor view: headline, attribute entries and the table."""

from dataclasses import replace
from datetime import date, datetime
from zoneinfo import ZoneInfo

from custom_components.ski_resort_recommender.lib.models import (
    CarPark,
    Connection,
    DayForecast,
    Drive,
    Leg,
    Resort,
    SnowRailOffer,
    SnowStation,
    WeatherPoint,
)
from custom_components.ski_resort_recommender.lib.scoring import DayScore
from custom_components.ski_resort_recommender.lib.service import (
    SNOW_N_RAIL_TAG,
    PointResult,
    Recommendation,
    RecommendationResult,
)
from custom_components.ski_resort_recommender.lib.settings import Settings
from custom_components.ski_resort_recommender.lib.view import (
    DIVIDER,
    detail,
    entry,
    headline,
    render_table,
    results_payload,
    scoring_info,
    sensor_state,
    sensor_table,
)
from custom_components.ski_resort_recommender.lib.weather_codes import WeatherIcon

ZURICH = ZoneInfo("Europe/Zurich")
SATURDAY = date(2026, 11, 28)
POINT = WeatherPoint(name="Leist", lat=47.06, lon=9.23, elevation_m=2222)


def at(hour: int, minute: int) -> datetime:
    """Return a time on the Saturday."""
    return datetime(2026, 11, 28, hour, minute, tzinfo=ZURICH)


TRAIN = Connection(
    departure=at(7, 38),
    platform="9",
    arrival=at(9, 18),
    duration_min=100,
    transfers=1,
    legs=(
        Leg("IC 3", "559", "Zürich HB", at(7, 38), "9", "Sargans", at(8, 32)),
        Leg(
            "B 441", None, "Sargans, Bahnhof", at(8, 36), "D", "Tannenboden", at(9, 18)
        ),
    ),
)


def make_recommendation(
    *, good: bool = True, train: bool = True, offer: bool = True, price: float = 76
) -> Recommendation:
    """Create a Flumserberg recommendation for Saturday."""
    resort = Resort(
        key="flumserberg",
        name="Flumserberg",
        points=(POINT,),
        meteoswiss_point_id=None,
        station="Flumserberg, Tannenboden",
        day_price_chf=price,
        snow_n_rail=SnowRailOffer("snownrail-flumserberg", 30) if offer else None,
    )
    day = DayForecast(
        day=SATURDAY,
        temp_min_c=-9,
        temp_max_c=-3,
        snowfall_cm=0,
        sunshine_hours=8,
        daylight_hours=9,
        weather_code=0,
        visibility_m=30_000,
        temp_ski_c=-5,
        gust_max_kmh=20,
        fresh_snow_cm=20,
    )
    return Recommendation(
        resort=resort,
        day=day,
        score=DayScore(83.24, reasons={"sun": 40.0}),
        is_good=good,
        point=POINT,
        connection=TRAIN if train else None,
        tags=(SNOW_N_RAIL_TAG,) if offer else (),
        weather_icon=WeatherIcon.SUNNY,
    )


def test_headline_follows_the_status() -> None:
    """Good day / No good day / No forecast yet."""
    good = RecommendationResult((make_recommendation(),))
    poor = RecommendationResult((make_recommendation(good=False),))

    assert headline(good) == "Good day"
    assert headline(poor) == "No good day"
    assert headline(RecommendationResult(())) == "No forecast yet"


def test_entry_holds_every_field_of_the_layout() -> None:
    """Classification, score, date, resort, icon, price, train, snow and rail."""
    e = entry(make_recommendation())

    assert e["classification"] == "Good day"
    assert e["is_good"] is True
    assert e["score"] == 83
    assert e["date"] == "2026-11-28"
    assert e["day"] == "Sat 28.11"
    assert e["resort"] == "Flumserberg"
    assert e["point"] == "Leist"
    assert e["weather_icon"] == "mdi:weather-sunny"
    assert e["price_chf"] == 76
    assert e["train"]["departure"] == "07:38"
    assert e["train"]["platform"] == "9"
    assert e["train"]["arrival"] == "09:18"
    assert e["train"]["summary"] == (
        "07:38 pl. 9 IC 3 (559) → Sargans, B 441 → 09:18 Tannenboden · 100 min"
    )
    assert e["snow_n_rail"] == {
        "up_to_pct": 30,
        "url": "https://freizeit.sbb.ch/en/stories/snownrail-flumserberg",
    }


def test_entry_without_train_and_offer() -> None:
    """Missing connection and no Snow'n'Rail offer are None."""
    e = entry(make_recommendation(good=False, train=False, offer=False))

    assert e["classification"] == "Not good"
    assert e["train"] is None
    assert e["snow_n_rail"] is None


def test_outlook_entry_is_classified_as_outlook() -> None:
    """The 4th entry (days 6-7) says Outlook."""
    assert entry(make_recommendation(), outlook=True)["classification"] == "Outlook"


def rows(table: str) -> list[str]:
    """Return the <tr> lines of a rendered table."""
    return [line for line in table.splitlines() if line.startswith("<tr>")]


def test_table_is_full_width_with_fixed_columns() -> None:
    """One table, 100 % wide; column widths without CSS (colgroup)."""
    table = render_table(RecommendationResult((make_recommendation(),)))

    assert table.startswith('<table width="100%">\n<colgroup>')
    assert table.splitlines()[1] == (
        '<colgroup><col width="104"><col width="64"><col width="32"><col>'
        '<col width="42"></colgroup>'
    )
    assert table.endswith("</table>")


def test_one_result_uses_three_rows_with_dep_and_arr_aligned() -> None:
    """Dep./Arr. in their own column, so the station names start aligned too."""
    first, second, third = rows(
        render_table(RecommendationResult((make_recommendation(),)))
    )

    assert first == (
        '<tr><td rowspan="3" align="center"><font size="5"><b>83</b></font><br>'
        '<font size="2">Good day ☀️</font></td>'
        '<td colspan="3"><b>Flumserberg</b> · <font size="2">Leist</font></td>'
        '<td rowspan="3" align="right">76.-<br><code>SnR</code></td></tr>'
    )
    assert second == (
        '<tr><td><font size="2">Sat 28.11</font></td>'
        '<td><font size="2">Dep.</font></td>'
        '<td><font size="2">Zürich HB, 07:38 · IC3 · Pl. 9</font></td></tr>'
    )
    assert third == (
        '<tr><td></td><td><font size="2">Arr.</font></td>'
        '<td><font size="2">Tannenboden, 09:18</font></td></tr>'
    )


def test_outlook_and_missing_train_offer_and_odd_price() -> None:
    """Outlook label; no train; no badge without offer; 76.50 with Rappen."""
    r = make_recommendation(train=False, offer=False, price=76.5)

    first, second, third = rows(render_table(RecommendationResult((), outlook=r)))

    assert '<font size="2">Outlook ☀️</font>' in first
    assert first.endswith('<td rowspan="3" align="right">76.50</td></tr>')
    assert second.endswith('<td></td><td><font size="2">No train</font></td></tr>')
    assert third == "<tr><td></td><td></td><td></td></tr>"


def test_names_are_html_escaped() -> None:
    """Resort names go into HTML: special characters are escaped."""
    r = make_recommendation()
    r = replace(r, resort=replace(r.resort, name="Arosa & Lenzerheide"))

    first = rows(render_table(RecommendationResult((r,))))[0]

    assert "<b>Arosa &amp; Lenzerheide</b>" in first


def test_table_without_results() -> None:
    """Nothing to show: the headline only."""
    assert render_table(RecommendationResult(())) == "No forecast yet"


ERROR = "Forecast update failed: Open-Meteo rate limit (HTTP 429 Too Many Requests)"


def test_without_data_the_state_says_no_data_yet() -> None:
    """First update failed: a visible state instead of a missing sensor."""
    assert sensor_state(None) == "No data yet"
    assert sensor_state(RecommendationResult(())) == "No forecast yet"


def test_without_data_the_table_shows_the_reason() -> None:
    """The dashboard card explains why it is empty."""
    assert sensor_table(None, ERROR) == f"⚠️ No data yet: {ERROR}"
    assert sensor_table(None, None) == "⚠️ No data yet"


def test_a_failed_update_keeps_the_last_result_with_a_note() -> None:
    """Older data stays visible; the note says the last update failed."""
    result = RecommendationResult((make_recommendation(),))

    table = sensor_table(result, ERROR)

    assert table.startswith(render_table(result))
    assert table.endswith(f"⚠️ Last update failed: {ERROR}. Showing the last result.")
    assert sensor_table(result, None) == render_table(result)


def test_results_are_separated_by_a_divider_row() -> None:
    """A full-width <hr> row between results, none before the first or after last."""
    result = RecommendationResult(
        (make_recommendation(), make_recommendation()), outlook=make_recommendation()
    )

    table_rows = rows(render_table(result))

    assert len(table_rows) == 3 * 3 + 2
    assert table_rows[3] == table_rows[7] == DIVIDER
    assert DIVIDER not in (table_rows[0], table_rows[-1])


def with_points(r: Recommendation) -> Recommendation:
    """Give a recommendation its (single) point result."""
    return replace(r, points=(PointResult(point=POINT, day=r.day, score=r.score),))


def test_detail_has_points_forecast_and_full_connection() -> None:
    """Everything the expanded row shows."""
    d = detail(with_points(make_recommendation()))

    assert d["resort"] == "Flumserberg"
    assert d["points"] == [
        {
            "name": "Leist",
            "weight": 1.0,
            "elevation_m": 2222,
            "score": 83,
            "reasons": {"sun": 40.0},
            "forecast": {
                "sunshine_hours": 8,
                "daylight_hours": 9,
                "fresh_snow_cm": 20,
                "snow_depth_cm": None,
                "gust_max_kmh": 20,
                "temp_ski_c": -5,
                "visibility_m": 30_000,
                "recent_rain_mm": None,
                "snow_after_rain_cm": None,
                "weather_code": 0,
            },
        }
    ]
    assert [leg["line"] for leg in d["train"]["legs"]] == ["IC 3", "B 441"]
    assert d["train"]["legs"][0] == {
        "line": "IC 3",
        "train_number": "559",
        "from": "Zürich HB",
        "departure": "07:38",
        "platform": "9",
        "to": "Sargans",
        "arrival": "08:32",
    }


def test_scoring_info_lists_the_weights_for_the_formula() -> None:
    """Current weights and thresholds (from the settings) for the legend."""
    info = scoring_info(Settings())

    assert info["min_good_score"] == 60
    assert info["weights"]["sun_points"] == 45
    assert info["weights"]["icy_penalty"] == 40
    assert info["ranking_days"] == 5


def test_results_payload_lists_all_results_best_first() -> None:
    """The modal gets the headline, every result and the scoring info."""
    good = with_points(make_recommendation())
    poor = with_points(replace(make_recommendation(good=False), outlook=True))
    result = RecommendationResult((good,), outlook=poor, all=(good, poor))

    payload = results_payload(result, Settings())

    assert payload["headline"] == "Good day"
    assert [r["classification"] for r in payload["results"]] == ["Good day", "Outlook"]
    assert payload["scoring"]["min_good_score"] == 60


def test_entry_train_has_stations_and_first_line_for_the_card() -> None:
    """The card shows Dep./Arr. stations and the first train from the attributes."""
    train = entry(make_recommendation())["train"]

    assert (train["from"], train["to"], train["line"]) == (
        "Zürich HB",
        "Tannenboden",
        "IC 3",
    )


def test_detail_lists_the_snow_stations_with_their_measurement() -> None:
    """The modal names the SLF stations behind the snow depth."""
    station = SnowStation(code="FLU2", name="Test", elevation_m=2100)
    r = make_recommendation()
    r = replace(r, resort=replace(r.resort, snow_stations=(station,)))

    d = detail(r, {"FLU2": 82.4})

    assert d["snow_stations"] == [
        {"code": "FLU2", "name": "Test", "elevation_m": 2100, "depth_cm": 82.4}
    ]
    assert detail(r)["snow_stations"][0]["depth_cm"] is None


def test_a_good_outlook_day_is_marked_good_for_the_color_mode() -> None:
    """The card colours good days; an outlook day keeps its label but is good."""
    e = entry(make_recommendation(), outlook=True)

    assert (e["classification"], e["is_good"]) == ("Outlook", True)
    assert entry(make_recommendation(good=False))["is_good"] is False


DRIVE = Drive(access="Tannenboden", duration_min=65, distance_km=72.4)


def test_entry_car_has_access_point_time_and_distance() -> None:
    """The card shows where to drive, how long and how far."""
    car = entry(replace(make_recommendation(), drive=DRIVE))["car"]

    assert car == {
        "access": "Tannenboden",
        "duration_min": 65,
        "distance_km": 72.4,
        "summary": "Tannenboden · 1:05 h · 72 km",
        "parking": [],
        "chargers": None,
    }
    assert entry(make_recommendation())["car"] is None


def test_table_adds_a_car_row_and_drops_no_train_in_car_mode() -> None:
    """Train + car: four rows; car only: the date moves to the car row."""
    both = rows(
        render_table(
            RecommendationResult((replace(make_recommendation(), drive=DRIVE),))
        )
    )
    car_only = rows(
        render_table(
            RecommendationResult(
                (replace(make_recommendation(train=False), drive=DRIVE),)
            )
        )
    )

    assert len(both) == 4
    assert 'rowspan="4"' in both[0]
    assert "Car" in both[3]
    assert "Tannenboden · 1:05 h · 72 km" in both[3]
    assert len(car_only) == 2
    assert "Sat 28.11" in car_only[1]
    assert "Car" in car_only[1]
    assert "No train" not in "".join(car_only)


STENNA = CarPark("Stenna", 46.833, 9.282, spaces=1147, price_chf=13.6, walk_m=178)


def test_car_entry_lists_the_car_parks_with_walking_minutes() -> None:
    """Spaces, price for a ski day, walk (80 m/min, 1.3 x the straight line)."""
    drive = replace(DRIVE, parking=(STENNA, CarPark("Free", 0, 0, price_chf=0)))

    parking = entry(replace(make_recommendation(), drive=drive))["car"]["parking"]

    assert parking == [
        {"name": "Stenna", "spaces": 1147, "price_chf": 13.6, "walk_min": 3},
        {"name": "Free", "spaces": None, "price_chf": 0, "walk_min": 1},
    ]


def test_table_shows_the_parking_price_under_the_ski_ticket() -> None:
    """Ski ticket and parking are separate values; free parking says so."""
    paid = replace(make_recommendation(), drive=replace(DRIVE, parking=(STENNA,)))
    free = replace(paid, drive=replace(DRIVE, parking=(replace(STENNA, price_chf=0),)))
    unknown = replace(
        paid, drive=replace(DRIVE, parking=(replace(STENNA, price_chf=None),))
    )

    assert "76.-<br>" in rows(render_table(RecommendationResult((paid,))))[0]
    assert "P 13.60" in rows(render_table(RecommendationResult((paid,))))[0]
    assert "P free" in rows(render_table(RecommendationResult((free,))))[0]
    assert "P " not in rows(render_table(RecommendationResult((unknown,))))[0]


def test_car_entry_counts_the_chargers_and_their_power() -> None:
    """Electric car: count, slowest and fastest kW (0 = unknown power)."""
    drive = replace(DRIVE, chargers_kw=(50.0, 22.0, 22.0, 0.0))

    car = entry(replace(make_recommendation(), drive=drive))["car"]

    assert car["chargers"] == {"count": 4, "kw_min": 22.0, "kw_max": 50.0}
    assert car["summary"] == "Tannenboden · 1:05 h · 72 km · ⚡4"


def test_car_entry_without_charger_data_says_nothing() -> None:
    """Not checked or no data around: no count (not a misleading 0)."""
    car = entry(replace(make_recommendation(), drive=DRIVE))["car"]
    no_chargers = entry(
        replace(make_recommendation(), drive=replace(DRIVE, chargers_kw=()))
    )

    assert car["chargers"] is None
    assert "⚡" not in car["summary"]
    assert no_chargers["car"]["chargers"] == {
        "count": 0,
        "kw_min": None,
        "kw_max": None,
    }
