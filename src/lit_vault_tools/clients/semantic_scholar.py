"""Semantic Scholar client: a paper's references/citations as `Neighbor`s, and batch details.

WHY THIS EXISTS
---------------
Explore needs one focus paper's neighbours fast and cheaply. Semantic Scholar
cannot sort citations server-side, so `fetch_neighbors` pages the whole list with
a *lean* field set (no abstract or tldr; 1000 per call) and Explore ranks locally;
`fetch_details` then fetches abstract / tldr / authors / venue for only the ranked
top slice through `/paper/batch`, in chunks of at most 500 ids.

* The API key goes in the `x-api-key` header, exactly as recorded in
  `tests/fixtures/README.md`. It is case-sensitive, which is why transport is
  `http.client` and not `urllib` (decision 12). The key is never in a URL, a
  `ClientError` or a log record.
* Rate limit (decision 18): requests are spaced at least `S2_MIN_INTERVAL_S`
  apart by a `Pacer`. Spacing only works across calls if they share one `Pacer`,
  so Explore creates one and passes it to every call; without one each call gets
  its own, which still spaces the pages within that call. A 429 is retried after
  each wait in `S2_BACKOFF_S` in turn, then raises `ClientError(429)` (5 requests
  in all). Any other failure, 404 included, raises at once with no retry.
* `sleep` and `clock` are injected so tests never wait.
* Hidden references: for many paywalled papers the publisher has Semantic
  Scholar hide the list, and `/references` answers 200 with `"data": null`.
  That is `ReferencesHidden`, deliberately NOT a `ClientError`: it is not a
  failure and must never be mistaken for an empty list, because Explore falls
  back to Crossref for it (decision 17). `"data": []` is a genuinely empty list.
* A neighbour without a `paperId` cannot be a stub (identity is the id,
  invariant 3), so it is skipped.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable, Sequence
from typing import NamedTuple
from urllib.parse import quote

from lit_vault_tools.clients.http import ClientError, HttpResponse, Transport
from lit_vault_tools.config import S2_BACKOFF_S, S2_BATCH_SIZE, S2_MIN_INTERVAL_S, S2_PAGE_LIMIT
from lit_vault_tools.domain.doi import normalize_doi
from lit_vault_tools.domain.neighbors import Neighbor

logger = logging.getLogger(__name__)

_BASE = "https://api.semanticscholar.org/graph/v1"
_LEAN_FIELDS = "title,year,citationCount,externalIds,isInfluential"
_DETAIL_FIELDS = "abstract,tldr,authors,venue"
_ENTRY_KEY = {"reference": "citedPaper", "citation": "citingPaper"}
_PATH = {"reference": "references", "citation": "citations"}

Sleep = Callable[[float], None]
Clock = Callable[[], float]


class ReferencesHidden(Exception):
    """The publisher hid this paper's reference list (`"data": null`); not an error, not empty."""


class Details(NamedTuple):
    abstract: str | None
    tldr: str | None
    authors: tuple[str, ...]
    venue: str | None


class Pacer:
    """Spaces request starts at least `interval` apart and runs the 429 backoff waits."""

    def __init__(
        self,
        sleep: Sleep = time.sleep,
        clock: Clock = time.monotonic,
        interval: float = S2_MIN_INTERVAL_S,
    ) -> None:
        self.sleep = sleep
        self.clock = clock
        self.interval = interval
        self._last: float | None = None

    def wait_turn(self) -> None:
        if self._last is not None:
            remaining = self.interval - (self.clock() - self._last)
            if remaining > 0:
                self.sleep(remaining)
        self._last = self.clock()


def _send(
    pacer: Pacer,
    transport: Transport,
    method: str,
    url: str,
    api_key: str,
    body: bytes | None = None,
) -> HttpResponse:
    """One paced request, retrying a 429 after each backoff wait; raises ClientError past the last."""
    headers = {"x-api-key": api_key}
    if body is not None:
        headers = {"Content-Type": "application/json", **headers}
    waits = iter(S2_BACKOFF_S)
    while True:
        pacer.wait_turn()
        logger.debug("S2 %s %s", method, url)
        response = transport(method, url, headers, body)
        if response.status != 429:
            return response
        wait = next(waits, None)
        if wait is None:
            raise ClientError(429, url)
        logger.info("Semantic Scholar rate limit; waiting %ss", wait)
        pacer.sleep(wait)


def _ok(response: HttpResponse, url: str) -> bytes:
    if not 200 <= response.status < 300:
        raise ClientError(response.status, url)
    return response.body


def _pacer(pacer: Pacer | None, sleep: Sleep, clock: Clock) -> Pacer:
    return pacer or Pacer(sleep, clock)


def fetch_s2_paper_id(
    doi: str,
    api_key: str,
    transport: Transport,
    sleep: Sleep = time.sleep,
    clock: Clock = time.monotonic,
    pacer: Pacer | None = None,
) -> str | None:
    """Semantic Scholar's paper id for a DOI; `None` when it answers 404."""
    bare = normalize_doi(doi)
    if bare is None:
        return None
    url = f"{_BASE}/paper/DOI:{quote(bare, safe='/:()')}?fields=paperId"
    response = _send(_pacer(pacer, sleep, clock), transport, "GET", url, api_key)
    if response.status == 404:
        return None
    return json.loads(_ok(response, url)).get("paperId")


def fetch_neighbors(
    paper_ref: str,
    relation: str,
    api_key: str,
    transport: Transport,
    sleep: Sleep = time.sleep,
    clock: Clock = time.monotonic,
    pacer: Pacer | None = None,
) -> list[Neighbor]:
    """Every reference or citation of `paper_ref` (`DOI:<doi>` or an s2 id), lean fields only."""
    pacer = _pacer(pacer, sleep, clock)
    base = f"{_BASE}/paper/{quote(paper_ref, safe='/:()')}/{_PATH[relation]}"
    neighbors: list[Neighbor] = []
    offset: int | None = 0
    while offset is not None:
        url = f"{base}?fields={_LEAN_FIELDS}&limit={S2_PAGE_LIMIT}&offset={offset}"
        page = json.loads(_ok(_send(pacer, transport, "GET", url, api_key), url))
        if page.get("data") is None:
            if relation == "reference":
                raise ReferencesHidden(paper_ref)
            logger.warning("no citation data for %s", paper_ref)
            break
        for item in page["data"]:
            neighbor = _neighbor(item, relation)
            if neighbor is not None:
                neighbors.append(neighbor)
        offset = page.get("next")
    return neighbors


def _neighbor(item: dict, relation: str) -> Neighbor | None:
    paper = item.get(_ENTRY_KEY[relation]) or {}
    if not paper.get("paperId"):
        logger.debug("skipping a %s with no paperId", relation)
        return None
    return Neighbor(
        s2_id=paper["paperId"],
        doi=normalize_doi((paper.get("externalIds") or {}).get("DOI")),
        title=paper.get("title"),
        authors=(),
        year=paper.get("year"),
        venue=None,
        citation_count=paper.get("citationCount"),
        is_influential=bool(item.get("isInfluential")),
        tldr=None,
        abstract=None,
        relation=relation,
    )


def fetch_details(
    s2_ids: Sequence[str],
    api_key: str,
    transport: Transport,
    sleep: Sleep = time.sleep,
    clock: Clock = time.monotonic,
    pacer: Pacer | None = None,
) -> dict[str, Details]:
    """abstract / tldr / authors / venue per id, in POST chunks of `S2_BATCH_SIZE`; unknown ids are absent."""
    pacer = _pacer(pacer, sleep, clock)
    url = f"{_BASE}/paper/batch?fields={_DETAIL_FIELDS}"
    details: dict[str, Details] = {}
    for start in range(0, len(s2_ids), S2_BATCH_SIZE):
        body = json.dumps({"ids": list(s2_ids[start : start + S2_BATCH_SIZE])}).encode()
        entries = json.loads(_ok(_send(pacer, transport, "POST", url, api_key, body), url))
        for entry in entries:
            if entry is None or not entry.get("paperId"):
                continue
            details[entry["paperId"]] = Details(
                abstract=entry.get("abstract"),
                tldr=(entry.get("tldr") or {}).get("text"),
                authors=tuple(a["name"] for a in entry.get("authors") or [] if a.get("name")),
                venue=entry.get("venue") or None,
            )
    return details
