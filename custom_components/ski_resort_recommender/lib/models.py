"""Data objects: Resort, WeatherPoint, DayForecast and train Connection."""

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True, slots=True)
class WeatherPoint:
    """One forecast location inside a resort (a lift station in the ski area)."""

    name: str
    lat: float
    lon: float
    elevation_m: int  # passed to Open-Meteo for the temperature downscaling
    weight: float = 1.0  # share in the resort's weighted average


@dataclass(frozen=True, slots=True)
class SnowRailOffer:
    """SBB Snow'n'Rail offer (train + ski pass); availability is not checked yet."""

    offer: str  # slug of the SBB RailAway story, e.g. "snownrail-pizol"
    up_to_pct: int  # maximum discount as advertised

    @property
    def url(self) -> str:
        """SBB RailAway page of the offer."""
        return f"https://freizeit.sbb.ch/en/stories/{self.offer}"


@dataclass(frozen=True, slots=True)
class AccessPoint:
    """Valley station with parking where you arrive by car (e.g. Flims, Laax)."""

    name: str
    lat: float
    lon: float


@dataclass(frozen=True, slots=True)
class Drive:
    """Car trip from home to the closest access point of a resort."""

    access: str  # name of the access point
    duration_min: int  # without traffic
    distance_km: float


@dataclass(frozen=True, slots=True)
class SnowStation:
    """SLF IMIS station that measures the snow depth near the resort."""

    code: str  # station code, e.g. "CMA2"
    name: str
    elevation_m: int


@dataclass(frozen=True)
class Resort:
    """Every resort follows the same logic."""

    key: str
    name: str
    points: tuple[WeatherPoint, ...]
    meteoswiss_point_id: int | None
    station: str  # train connection (base station)
    day_price_chf: float | None
    snow_n_rail: SnowRailOffer | None = None
    # measured base (median of the stations); none: the model snow depth is used
    snow_stations: tuple[SnowStation, ...] = ()
    # by car: the closest of these wins; none: no drive time
    access: tuple[AccessPoint, ...] = ()


@dataclass(frozen=True, slots=True)
class DayForecast:
    """Response from fetching the weather api."""

    day: date
    temp_min_c: float | None
    temp_max_c: float | None
    snowfall_cm: float | None  # snowfall of the whole day
    sunshine_hours: float | None
    daylight_hours: float | None
    weather_code: int | None  # daily code = most severe condition of the day
    # hourly values reduced to one per day
    visibility_m: float | None  # median over the ski hours (DWD only)
    temp_ski_c: float | None  # mean over the ski hours
    gust_max_kmh: float | None  # max gust over the ski hours
    fresh_snow_cm: float | None  # snowfall in the 48 h before opening
    weather_codes_ski: tuple[int, ...] = ()  # hourly codes in the ski hours
    recent_rain_mm: float | None = None  # rain + showers in the 48 h before opening
    snow_after_rain_cm: float | None = None  # snowfall after the last rain hour
    # snow on the ground at opening: measured base + model change, else model only
    snow_depth_cm: float | None = None

    @property
    def has_data(self) -> bool:
        """Return True if there are usable values (False beyond the model horizon)."""
        return any(
            value is not None
            for value in (self.weather_code, self.sunshine_hours, self.temp_max_c)
        )


@dataclass(frozen=True, slots=True)
class Leg:
    """One train/bus ride of a connection."""

    line: str  # e.g. "IC 3", "B 81"
    train_number: str | None  # e.g. "1057"
    departure_station: str
    departure: datetime
    platform: str | None
    arrival_station: str
    arrival: datetime


@dataclass(frozen=True, slots=True)
class Connection:
    """A public transport connection from the home station to a resort."""

    departure: datetime
    platform: str | None
    arrival: datetime
    duration_min: int
    transfers: int
    legs: tuple[Leg, ...]


# resort key -> point name -> one DayForecast per day
type Forecasts = dict[str, dict[str, list[DayForecast]]]
