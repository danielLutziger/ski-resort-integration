"""Explicit scoring values for the tests (the current defaults, written out)."""

from custom_components.ski_resort_recommender.lib.settings import ScoringSettings

SCORING = ScoringSettings(
    sun_points=30,
    sun_full_hours=8,
    snow_points=20,
    snow_full_cm=25,
    wind_limit_kmh=30,
    wind_penalty=25,
    wind_penalty_step_kmh=30,
    temp_good_min_c=-8,
    temp_good_max_c=2,
    temp_slush_c=5,
    temp_good_points=20,
    temp_ok_points=10,
    temp_slush_points=-10,
    weather_very_good_points=0,
    weather_neutral_points=0,
    weather_bad_points=-15,
    weather_no_go_points=-50,
    visibility_good_m=5000,
    visibility_bad_m=1000,
    visibility_penalty=30,
)
