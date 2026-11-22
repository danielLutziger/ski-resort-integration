"""Data objects: Resort, WeatherPoint and DayForecast."""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class WeatherPoint:
    """One forecast location inside a resort (a lift station in the ski area)."""

    name: str
    lat: float
    lon: float
    elevation_m: int  # passed to Open-Meteo for the temperature downscaling
    weight: float = 1.0  # share in the resort's weighted average


@dataclass(frozen=True)
class Resort:
    """Every resort follows the same logic."""

    key: str
    name: str
    points: tuple[WeatherPoint, ...]
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
    visibility_m: float | None

    @property
    def has_data(self) -> bool:
        """Return True if there are usable values (False beyond the model horizon)."""
        return any(
            value is not None
            for value in (self.weather_code, self.sunshine_hours, self.temp_max_c)
        )


# resort key -> point name -> one DayForecast per day
type Forecasts = dict[str, dict[str, list[DayForecast]]]
