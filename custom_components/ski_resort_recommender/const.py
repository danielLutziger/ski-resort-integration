"""Constants for the Ski Resort Recommender."""

from datetime import timedelta
from logging import Logger, getLogger

LOGGER: Logger = getLogger(__package__)

DOMAIN = "ski_resort_recommender"
NAME = "Ski Resort Recommender"
ATTRIBUTION = "Weather data by Open-Meteo.com"
# the coordinator runs hourly (new day, SBB); Open-Meteo only every weather interval
UPDATE_INTERVAL = timedelta(hours=1)
# config entry options (config flow later)
CONF_HOME_STATION = "home_station"
# Open-Meteo budget: ~100 points x 2 requests (> 10 variables); raise if rate limited
CONF_WEATHER_INTERVAL_HOURS = "weather_interval_hours"
DEFAULT_WEATHER_INTERVAL_HOURS = 3
