"""Data objects: Resort and DayForecast."""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Resort:
    """Every resort follows the same logic."""

    # add elevation to resort for different values (base, mid, peak)
    key: str
    name: str
    lat: float
    lon: float
    meteoswiss_point_id: int | None
    station: str  # train connection (base station)
    day_price_chf: float | None


@dataclass(frozen=True, slots=True)
class DayForecast:
    """Response from fetching the weather api."""

    day: date
    temp_min_c: float | None
    temp_max_c: float | None
    snowfall_cm: float | None
    sunshine_hours: float | None
    wind_max_kmh: float | None
    weather_code: int | None
    vision: int | None

    @property
    def has_data(self) -> bool:
        """Return True if there are usable values (False beyond the model horizon)."""
        return any(
            value is not None
            for value in (self.weather_code, self.sunshine_hours, self.temp_max_c)
        )
