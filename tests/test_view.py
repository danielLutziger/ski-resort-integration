"""Tests for the sensor view: headline, attribute entries and the table."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from custom_components.ski_resort_recommender.lib.models import (
    Connection,
    DayForecast,
    Leg,
    Resort,
    SnowRailOffer,
    WeatherPoint,
)
from custom_components.ski_resort_recommender.lib.scoring import DayScore
from custom_components.ski_resort_recommender.lib.service import (
    SNOW_N_RAIL_TAG,
    Recommendation,
    RecommendationResult,
)
from custom_components.ski_resort_recommender.lib.view import (
    entry,
    headline,
    render_table,
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


def test_table_has_the_three_rows_per_recommendation() -> None:
    """classification|score / date|resort|icon|price / train|snow and rail."""
    result = RecommendationResult(
        (make_recommendation(),), outlook=make_recommendation(good=False, offer=False)
    )

    table = render_table(result)
    blocks = table.split("\n\n---\n\n")

    assert len(blocks) == 2
    first = blocks[0].splitlines()
    assert first[0] == "| **Good day** | **83** | | |"
    assert first[1] == "|:--|:--|:-:|--:|"
    assert first[2] == "| Sat 28.11 | Flumserberg (Leist) | ☀️ | CHF 76 |"
    assert first[3] == (
        "| 🚆 07:38 pl. 9 IC 3 (559) → Sargans, B 441 → 09:18 Tannenboden · 100 min"
        " | [🎿 Snow'n'Rail up to 30 %]"
        "(https://freizeit.sbb.ch/en/stories/snownrail-flumserberg) | | |"
    )
    outlook = blocks[1].splitlines()
    assert outlook[0] == "| **Outlook** | **83** | | |"
    assert outlook[3].endswith("| - | | |")


def test_table_without_results() -> None:
    """Nothing to show: the headline only."""
    assert render_table(RecommendationResult(())) == "No forecast yet"
