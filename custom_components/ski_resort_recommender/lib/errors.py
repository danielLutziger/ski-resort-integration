"""Exceptions raised by the providers, and readable messages for them."""

import aiohttp

TOO_MANY_REQUESTS = 429


class SkiApiError(Exception):
    """Base class for all exceptions in our API."""


class SkiApiConnectionError(SkiApiError):
    """API could not be reached."""


class SkiApiParseError(SkiApiError):
    """API answered, but response didnt match input."""


def describe(source: str, error: BaseException) -> str:
    """Short message for the sensor and the log (no request URL)."""
    if isinstance(error, aiohttp.ClientResponseError):
        reason = f"HTTP {error.status} {error.message}".strip()
        if error.status == TOO_MANY_REQUESTS:
            return f"{source} rate limit ({reason})"
        return f"{source} {reason}"
    if isinstance(error, TimeoutError):
        return f"{source} timeout"
    return f"{source} unreachable ({type(error).__name__})"
