"""A fake aiohttp session for the provider tests (no network)."""

from http import HTTPStatus
from typing import TYPE_CHECKING, Any, Self

import aiohttp
from multidict import CIMultiDict, CIMultiDictProxy
from yarl import URL

if TYPE_CHECKING:
    from collections.abc import Callable


class FakeResponse:
    """Async context manager like aiohttp's response: payload, status or error."""

    def __init__(
        self,
        payload: Any = None,
        *,
        status: int = 200,
        error: BaseException | None = None,
    ) -> None:
        """Answer with payload and status, or raise error when the request starts."""
        self._payload = payload
        self._status = status
        self._error = error

    async def __aenter__(self) -> Self:
        """Start the request: raise the configured error, if any."""
        if self._error:
            raise self._error
        return self

    async def __aexit__(self, *exc: object) -> None:
        """Nothing to clean up."""

    def raise_for_status(self) -> None:
        """Raise like aiohttp for 4xx/5xx answers."""
        if self._status >= 400:
            url = URL("https://example.invalid")
            info = aiohttp.RequestInfo(url, "GET", CIMultiDictProxy(CIMultiDict()), url)
            raise aiohttp.ClientResponseError(
                info, (), status=self._status, message=HTTPStatus(self._status).phrase
            )

    async def json(self) -> Any:
        """Return the payload."""
        return self._payload


class FakeSession:
    """Records the requests and answers with respond(url, params)."""

    def __init__(self, respond: Callable[[str, dict], FakeResponse]) -> None:
        """Use respond to build the answer of every request."""
        self._respond = respond
        self.calls: list[dict] = []

    def get(self, url: str, *, params: dict, timeout: object = None) -> FakeResponse:  # noqa: ARG002
        """Return the fake response for this request."""
        self.calls.append(params)
        return self._respond(url, params)
