"""The config flow module loads and its form covers every option."""

from custom_components.ski_resort_recommender import config_flow
from custom_components.ski_resort_recommender.lib import options
from custom_components.ski_resort_recommender.lib.settings import Settings


def test_options_form_has_a_field_for_every_option() -> None:
    """Building the selectors at import time works; no option is missing."""
    fields = {str(key) for key in config_flow.OPTIONS_SCHEMA.schema}

    assert fields == set(options.options_from_settings(Settings()))


def test_default_form_values_pass_the_schema() -> None:
    """The pre-filled defaults are valid input for the form."""
    values = options.options_from_settings(Settings())
    values.pop(options.HOME_STATION)  # optional, empty by default

    config_flow.OPTIONS_SCHEMA(values)
