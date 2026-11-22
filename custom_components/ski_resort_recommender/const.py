"""Constants for the Ski Resort Recommender."""

from datetime import timedelta
from logging import Logger, getLogger

LOGGER: Logger = getLogger(__package__)

DOMAIN = "ski_resort_recommender"
NAME = "Ski Resort Recommender"
ATTRIBUTION = "Weather data by Open-Meteo.com"
# the coordinator runs hourly (new day, SBB); Open-Meteo only every weather interval
UPDATE_INTERVAL = timedelta(hours=1)
# option keys and their conversion to Settings: lib/options.py
