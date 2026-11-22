"""Constants for the Ski Resort Recommender."""

from datetime import timedelta
from logging import Logger, getLogger

LOGGER: Logger = getLogger(__package__)

DOMAIN = "ski_resort_recommender"
NAME = "Ski Resort Recommender"
ATTRIBUTION = "Weather data by Open-Meteo.com"
# Open-Meteo budget: 101 points x 2 requests (> 10 variables) -> not hourly
UPDATE_INTERVAL = timedelta(hours=3)
# config entry option: home station for the train connections (config flow later)
CONF_HOME_STATION = "home_station"
