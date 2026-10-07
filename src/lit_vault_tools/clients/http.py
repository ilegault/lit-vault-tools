"""HTTP transport shared by every client.

WHY THIS EXISTS
---------------
Decision 12: the project has no runtime dependencies, so HTTP is the standard
library's `http.client` behind an injectable `Transport`; tests pass a fake that
replays saved responses.

It is deliberately NOT `urllib`: urllib re-capitalises header names
(`x-api-key` becomes `X-api-key`) and Semantic Scholar's key header is
case-sensitive, so every request would silently go out unauthenticated.
`http.client` sends header names exactly as given.

* A non-success status is not an error here: `stdlib_transport` returns it and
  the client decides (404 is "not found", 429/500 are `ClientError`).
* `ClientError` redacts any `api_key=` query value from the URL it reports,
  because OpenAlex takes its key in the query string and an exception message
  ends up in terminal output and logs.
* Redirects (301/302/303/307/308) are followed a bounded number of times.
"""

from __future__ import annotations

import http.client
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urljoin, urlsplit

_TIMEOUT_SECONDS = 30
_MAX_REDIRECTS = 5
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_KEY_PARAM = re.compile(r"(api_key=)[^&#]*", re.IGNORECASE)


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: bytes


class Transport(Protocol):
    def __call__(
        self, method: str, url: str, headers: Mapping[str, str], body: bytes | None
    ) -> HttpResponse: ...


class ClientError(Exception):
    """A non-success status other than 404. The message never contains an API key."""

    def __init__(self, status: int, url: str) -> None:
        self.status = status
        self.url = _KEY_PARAM.sub(r"\1REDACTED", url)
        super().__init__(f"HTTP {status} for {self.url}")


def stdlib_transport(
    method: str, url: str, headers: Mapping[str, str], body: bytes | None
) -> HttpResponse:
    """Send one request with `http.client`, following redirects; never raises on status."""
    for _ in range(_MAX_REDIRECTS + 1):
        parts = urlsplit(url)
        connection_class: Callable[..., http.client.HTTPConnection] = (
            http.client.HTTPSConnection if parts.scheme == "https" else http.client.HTTPConnection
        )
        connection = connection_class(parts.netloc, timeout=_TIMEOUT_SECONDS)
        target = parts.path or "/"
        if parts.query:
            target += "?" + parts.query
        try:
            connection.request(method, target, body=body, headers=dict(headers))
            response = connection.getresponse()
            data = response.read()
            location = response.getheader("Location")
            status = response.status
        finally:
            connection.close()
        if status not in _REDIRECT_STATUSES or not location:
            return HttpResponse(status, data)
        url = urljoin(url, location)
        if status in (301, 302, 303) and method != "GET":
            method, body = "GET", None
    raise ClientError(310, url)
