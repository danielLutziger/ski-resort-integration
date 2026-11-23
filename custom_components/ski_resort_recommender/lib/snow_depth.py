"""Measured snow depth (SLF stations) as the base of the forecast snow depth."""

from dataclasses import replace
from statistics import median
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import date

    from custom_components.ski_resort_recommender.lib.models import (
        DayForecast,
        Forecasts,
        Resort,
    )


def apply_measured_depth(
    resorts: list[Resort],
    forecasts: Forecasts,
    measured: Mapping[str, float],
    today: date,
) -> Forecasts:
    """
    Use the measured base plus the model's change instead of the model depth.

    The models read the snow depth too low (23.11: Laax 36-49 cm, measured 74 cm).
    Base = median of the resort's stations at today's opening (the median: one
    station that the wind has blown bare does not pull three stations down).
    Every point keeps its model change from today to the day (new snow, melting):
    depth = base + model(day) - model(today), at least 0. Resorts without a
    measured station keep the model values.
    """
    result = dict(forecasts)
    for resort in resorts:
        depths = [measured[s.code] for s in resort.snow_stations if s.code in measured]
        if not depths or resort.key not in forecasts:
            continue
        base = median(depths)
        result[resort.key] = {
            point: _with_base(days, base, today)
            for point, days in forecasts[resort.key].items()
        }
    return result


def _with_base(days: list[DayForecast], base: float, today: date) -> list[DayForecast]:
    """Shift one point's snow depths so that today's opening equals the base."""
    ref = next((d.snow_depth_cm for d in days if d.day == today), None)
    return [replace(d, snow_depth_cm=_depth(d.snow_depth_cm, ref, base)) for d in days]


def _depth(model: float | None, ref: float | None, base: float) -> float:
    """Return the base plus the model change (the base alone without model values)."""
    if model is None or ref is None:
        return base
    return max(base + model - ref, 0.0)
