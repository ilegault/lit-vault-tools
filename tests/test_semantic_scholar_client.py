"""Semantic Scholar client: only the transport, clock and sleep are faked; fixtures are real captured responses."""

import json
import logging
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from lit_vault_tools import config
from lit_vault_tools.clients.http import ClientError, HttpResponse
from lit_vault_tools.clients.semantic_scholar import (
    Pacer,
    ReferencesHidden,
    fetch_details,
    fetch_neighbors,
    fetch_s2_paper_id,
)
from lit_vault_tools.domain.doi import normalize_doi

FIXTURES = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


PAPER, PAGE1, LAST = load("s2_paper"), load("s2_references_page1"), load("s2_references_last")
CITATIONS, ELIDED, BATCH = load("s2_citations_page1"), load("s2_references_elided"), load("s2_batch")
KEY = "s2-secret-key-xyz"
DOI = "10.1016/j.matdes.2024.112730"


class FakeTime:
    def __init__(self):
        self.now = 1000.0
        self.sleeps = []

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class FakeTransport:
    """Serves scripted (status, payload) answers in order and records every request."""

    def __init__(self, script, time=None):
        self.script = list(script)
        self.time = time
        self.requests = []

    def __call__(self, method, url, headers, body):
        at = self.time.now if self.time else None
        self.requests.append({"method": method, "url": url, "headers": dict(headers), "body": body, "at": at})
        status, payload = self.script.pop(0) if len(self.script) > 1 else self.script[0]
        data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        return HttpResponse(status, data)


def query(url):
    return {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}


def call_neighbors(transport, relation="reference", time=None, ref=f"DOI:{DOI}", **extra):
    time = time or FakeTime()
    return fetch_neighbors(ref, relation, KEY, transport, sleep=time.sleep, clock=time.clock, **extra)


def test_reference_paging_follows_next_and_returns_every_item_in_order():
    transport = FakeTransport([(200, PAGE1), (200, LAST)])
    neighbors = call_neighbors(transport)
    raw = PAGE1["data"] + LAST["data"]
    assert [n.s2_id for n in neighbors] == [r["citedPaper"]["paperId"] for r in raw]
    for neighbor, item in zip(neighbors, raw, strict=True):
        paper = item["citedPaper"]
        assert neighbor.relation == "reference"
        assert neighbor.title == paper["title"]
        assert neighbor.year == paper["year"]
        assert neighbor.citation_count == paper["citationCount"]
        assert neighbor.is_influential == item["isInfluential"]
        assert neighbor.doi == normalize_doi((paper.get("externalIds") or {}).get("DOI"))
        assert neighbor.abstract is None and neighbor.tldr is None
    assert [query(r["url"])["offset"] for r in transport.requests] == ["0", str(PAGE1["next"])]


def test_lean_request_shape():
    transport = FakeTransport([(200, PAGE1), (200, LAST)])
    call_neighbors(transport)
    first = transport.requests[0]
    assert first["method"] == "GET"
    assert first["url"].startswith(f"https://api.semanticscholar.org/graph/v1/paper/DOI:{DOI}/references?")
    params = query(first["url"])
    assert params["limit"] == "1000"
    assert "abstract" not in params["fields"] and "tldr" not in params["fields"]
    assert params["fields"] == "title,year,citationCount,externalIds,isInfluential"
    assert first["headers"] == {"x-api-key": KEY}


def test_citations_read_citing_paper():
    transport = FakeTransport([(200, CITATIONS), (200, {"offset": 5, "data": []})])
    neighbors = call_neighbors(transport, "citation")
    assert [n.s2_id for n in neighbors] == [c["citingPaper"]["paperId"] for c in CITATIONS["data"]]
    assert all(n.relation == "citation" for n in neighbors)
    assert "/citations?" in transport.requests[0]["url"]


def test_hidden_references_raise_references_hidden_not_client_error():
    with pytest.raises(ReferencesHidden) as info:
        call_neighbors(FakeTransport([(200, ELIDED)]))
    assert not isinstance(info.value, ClientError)


def test_empty_data_list_is_an_empty_result_not_hidden():
    assert call_neighbors(FakeTransport([(200, {"offset": 0, "data": []})])) == []


def test_neighbor_without_paper_id_is_skipped():
    unlinked = {"isInfluential": False, "citedPaper": {"paperId": None, "title": "x"}}
    page = {"offset": 0, "data": [unlinked, *LAST["data"]]}
    neighbors = call_neighbors(FakeTransport([(200, page)]))
    assert [n.s2_id for n in neighbors] == [r["citedPaper"]["paperId"] for r in LAST["data"]]


def test_details_chunks_of_500_and_null_entries_absent():
    entries = [e for e in BATCH if e is not None]

    class Batch(FakeTransport):
        def __call__(self, method, url, headers, body):
            ids = json.loads(body)["ids"]
            self.requests.append({"method": method, "url": url, "headers": dict(headers), "ids": ids})
            out = []
            for pid in ids:
                n = int(pid.removeprefix("id"))
                out.append(None if n % 6 == 5 else {**entries[n % len(entries)], "paperId": pid})
            return HttpResponse(200, json.dumps(out).encode())

    ids = [f"id{n:05d}" for n in range(1203)]
    time = FakeTime()
    transport = Batch([])
    details = fetch_details(ids, KEY, transport, sleep=time.sleep, clock=time.clock)
    assert [len(r["ids"]) for r in transport.requests] == [500, 500, 203]
    assert all(r["method"] == "POST" for r in transport.requests)
    assert transport.requests[0]["url"] == "https://api.semanticscholar.org/graph/v1/paper/batch?fields=abstract,tldr,authors,venue"
    assert transport.requests[0]["headers"] == {"Content-Type": "application/json", "x-api-key": KEY}
    expected_present = [pid for n, pid in enumerate(ids) if n % 6 != 5]
    assert sorted(details) == sorted(expected_present)
    first = entries[0]
    abstract, tldr, authors, venue = details["id00000"]
    assert abstract == first.get("abstract")
    assert tldr == (first["tldr"] or {}).get("text")
    assert authors == tuple(a["name"] for a in first["authors"])
    assert venue == first["venue"]


def test_requests_are_spaced_at_least_the_minimum_interval():
    time = FakeTime()
    transport = FakeTransport([(200, {**PAGE1, "next": 5}), (200, {**PAGE1, "next": 10}), (200, LAST)], time)
    call_neighbors(transport, time=time)
    starts = [r["at"] for r in transport.requests]
    assert len(starts) == 3
    assert all(b - a >= config.S2_MIN_INTERVAL_S - 1e-9 for a, b in zip(starts, starts[1:], strict=False))


def test_a_shared_pacer_spaces_requests_across_calls():
    time = FakeTime()
    pacer = Pacer(time.sleep, time.clock)
    transport = FakeTransport([(200, PAPER)], time)
    fetch_s2_paper_id(DOI, KEY, transport, pacer=pacer)
    fetch_s2_paper_id(DOI, KEY, transport, pacer=pacer)
    first, second = (r["at"] for r in transport.requests)
    assert second - first >= config.S2_MIN_INTERVAL_S - 1e-9


def test_paper_id_and_404():
    time = FakeTime()
    transport = FakeTransport([(200, PAPER)])
    assert fetch_s2_paper_id(DOI, KEY, transport, sleep=time.sleep, clock=time.clock) == PAPER["paperId"]
    assert transport.requests[0]["url"] == f"https://api.semanticscholar.org/graph/v1/paper/DOI:{DOI}?fields=paperId"
    assert fetch_s2_paper_id(DOI, KEY, FakeTransport([(404, {})]), sleep=time.sleep, clock=time.clock) is None


def test_429_is_retried_with_backoff_then_succeeds():
    time = FakeTime()
    transport = FakeTransport([(429, {}), (429, {}), (200, PAPER)])
    assert fetch_s2_paper_id(DOI, KEY, transport, sleep=time.sleep, clock=time.clock) == PAPER["paperId"]
    assert time.sleeps == [5, 10]
    assert len(transport.requests) == 3


def test_persistent_429_raises_after_exactly_five_requests():
    time = FakeTime()
    transport = FakeTransport([(429, {})])
    with pytest.raises(ClientError) as info:
        fetch_s2_paper_id(DOI, KEY, transport, sleep=time.sleep, clock=time.clock)
    assert info.value.status == 429
    assert len(transport.requests) == 5
    assert time.sleeps == list(config.S2_BACKOFF_S)


@pytest.mark.parametrize("status", [400, 403, 500])
def test_other_failures_raise_at_once_without_retry(status):
    time = FakeTime()
    transport = FakeTransport([(status, {})])
    with pytest.raises(ClientError) as info:
        call_neighbors(transport, time=time)
    assert info.value.status == status
    assert len(transport.requests) == 1 and time.sleeps == []


def test_neighbors_404_raises():
    with pytest.raises(ClientError) as info:
        call_neighbors(FakeTransport([(404, {})]))
    assert info.value.status == 404


def test_key_never_in_errors_or_logs(caplog):
    caplog.set_level(logging.DEBUG)
    time = FakeTime()
    for status in (200, 404, 429, 500):
        try:
            fetch_s2_paper_id(DOI, KEY, FakeTransport([(status, PAPER)]), sleep=time.sleep, clock=time.clock)
        except ClientError as err:
            assert KEY not in str(err) and KEY not in repr(err)
    assert all(KEY not in str(r.__dict__) for r in caplog.records)


def test_config_constants():
    assert config.S2_MIN_INTERVAL_S == 1.5
    assert config.S2_BACKOFF_S == (5, 10, 20, 40)


def test_tldr_text_is_taken_from_the_documented_object_shape():
    entry = {**[e for e in BATCH if e][0], "abstract": "An abstract.", "tldr": {"model": "tldr@v2", "text": "Short."}}
    transport = FakeTransport([(200, [entry])])
    time = FakeTime()
    details = fetch_details([entry["paperId"]], KEY, transport, sleep=time.sleep, clock=time.clock)
    assert details[entry["paperId"]].abstract == "An abstract."
    assert details[entry["paperId"]].tldr == "Short."
