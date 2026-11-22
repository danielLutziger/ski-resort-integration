class SkiApiError(Exception):
    """Base class for all exceptions in our API."""


class SkiApiConnectionError(SkiApiError):
    """API could not be reached."""


class SkiApiParseError(SkiApiError):
    """API answered, but response didnt match input."""
