from datetime import date

from custom_components.ski_resort_recommender.lib.models import DayForecast
from custom_components.ski_resort_recommender.lib.scoring import score_day


def test_sunny_cold_day_beats_rainy_day():
    sunny = DayForecast(
        day=date(2026, 12, 5),
        temp_min_c=-8,
        temp_max_c=2,
        snowfall_cm=0,
        sunshine_hours=8,
        wind_max_kmh=10,
        weather_code=0,
    )

    rainy = DayForecast(
        day=date(2026, 12, 5),
        temp_min_c=-8,
        temp_max_c=2,
        snowfall_cm=0,
        sunshine_hours=8,
        wind_max_kmh=10,
        weather_code=63,
    )

    assert score_day(sunny).total > score_day(rainy).total
