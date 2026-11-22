"""Explicit scoring values for the tests (the current defaults, written out)."""

from custom_components.ski_resort_recommender.lib.settings import ScoringSettings

SCORING = ScoringSettings(
    sun_points=60,
    sun_full_share=0.8,
    snow_points=40,
    snow_full_cm=30,
    gust_limit_kmh=40,
    gust_full_kmh=80,
    wind_penalty=30,
    temp_cold_c=-15,
    temp_cold_penalty=10,
    temp_slush_start_c=2,
    temp_slush_full_c=6,
    temp_slush_penalty=20,
    weather_very_good_points=0,
    weather_neutral_points=0,
    weather_bad_points=-15,
    weather_no_go_points=-50,
    no_go_min_hours=2,
    visibility_good_m=5000,
    visibility_bad_m=1000,
    visibility_penalty=30,
)
