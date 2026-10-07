"""OpenAlex client: only the transport is faked; it replays the real captured response."""

import json
import logging
from pathlib import Path

import pytest

from lit_vault_tools.clients.http import ClientError, HttpResponse
from lit_vault_tools.clients.openalex import fetch_work
from lit_vault_tools.domain.doi import normalize_doi
from lit_vault_tools.domain.people import AuthorRef, InstitutionRef

FIXTURE = Path(__file__).parent / "fixtures" / "openalex_work.json"
RAW = json.loads(FIXTURE.read_text(encoding="utf-8"))
DOI = "10.1016/j.matdes.2024.112730"
KEY = "test-secret-key-123"
PREFIX = "https://openalex.org/"


class FakeTransport:
    def __init__(self, status=200, body=None):
        self.status = status
        self.body = FIXTURE.read_bytes() if body is None else body
        self.calls = []

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, dict(headers), body))
        return HttpResponse(self.status, self.body)


def strip(value):
    return value.removeprefix(PREFIX)


def test_scalar_fields_come_from_fixture():
    record = fetch_work(DOI, KEY, FakeTransport())
    assert record.openalex_id == strip(RAW["id"])
    assert record.doi == normalize_doi(RAW["doi"])
    assert record.oa_status == RAW["open_access"]["oa_status"]
    assert record.references == [strip(r) for r in RAW["referenced_works"]]
    assert record.subfield == RAW["primary_topic"]["subfield"]["display_name"]
    assert record.reference_dois == []


def test_authors_one_per_authorship_in_order():
    record = fetch_work(DOI, KEY, FakeTransport())
    assert len(record.authors) == len(RAW["authorships"])
    for (ref, names), raw in zip(record.authors, RAW["authorships"], strict=True):
        assert ref == AuthorRef(strip(raw["author"]["id"]), raw["author"]["display_name"])
        assert names == [i["display_name"] for i in raw["institutions"]]


def test_institutions_and_countries_deduplicated_first_seen():
    record = fetch_work(DOI, KEY, FakeTransport())
    expected, seen = [], set()
    for a in RAW["authorships"]:
        for i in a["institutions"]:
            if i["id"] not in seen:
                seen.add(i["id"])
                expected.append(
                    InstitutionRef(strip(i["id"]), i["display_name"], i["ror"], i["country_code"], i.get("type"))
                )
    assert record.institutions == expected
    assert len(expected) < sum(len(a["institutions"]) for a in RAW["authorships"])
    countries = []
    for a in RAW["authorships"]:
        for c in a["countries"]:
            if c not in countries:
                countries.append(c)
    assert record.countries == countries


def test_404_returns_none():
    assert fetch_work(DOI, KEY, FakeTransport(404, b"{}")) is None


@pytest.mark.parametrize("status", [429, 500])
def test_error_statuses_raise_client_error(status):
    with pytest.raises(ClientError) as info:
        fetch_work(DOI, KEY, FakeTransport(status, b"{}"))
    assert info.value.status == status


def test_request_matches_recorded_shape():
    transport = FakeTransport()
    fetch_work(DOI, KEY, transport)
    method, url, headers, body = transport.calls[0]
    assert method == "GET"
    assert url == f"https://api.openalex.org/works/doi:{DOI}?api_key={KEY}"
    assert body is None
    assert KEY not in "".join(headers.keys()) + "".join(headers.values())


def test_key_never_in_error_or_logs(caplog):
    caplog.set_level(logging.DEBUG)
    for status in (200, 404, 429, 500):
        try:
            fetch_work(DOI, KEY, FakeTransport(status, b"{}" if status != 200 else None))
        except ClientError as err:
            assert KEY not in str(err)
            assert KEY not in repr(err)
    assert all(KEY not in r.getMessage() for r in caplog.records)
    assert all(KEY not in str(r.__dict__) for r in caplog.records)
