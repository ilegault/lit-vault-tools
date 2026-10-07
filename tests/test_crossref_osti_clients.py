"""Crossref and OSTI fallback clients: only the transport is faked, replaying real captured responses."""

import json
import logging
from pathlib import Path

import pytest

from lit_vault_tools.clients import crossref, osti
from lit_vault_tools.clients.http import ClientError, HttpResponse
from lit_vault_tools.domain.doi import normalize_doi

FIXTURES = Path(__file__).parent / "fixtures"
CROSSREF_RAW = json.loads((FIXTURES / "crossref_work.json").read_text(encoding="utf-8"))
OSTI_RAW = json.loads((FIXTURES / "osti_record.json").read_text(encoding="utf-8"))
DOI = "10.1016/j.matdes.2024.112730"
MAILTO = "someone-test@example.org"
TITLE = OSTI_RAW[0]["title"]


class FakeTransport:
    def __init__(self, body, status=200):
        self.body = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.status = status
        self.calls = []

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, dict(headers), body))
        return HttpResponse(self.status, self.body)


def test_crossref_reference_dois_normalized_in_order_skipping_missing():
    record = crossref.fetch_work(DOI, MAILTO, FakeTransport(CROSSREF_RAW))
    expected = [normalize_doi(r["DOI"]) for r in CROSSREF_RAW["message"]["reference"] if r.get("DOI")]
    assert record.reference_dois == expected
    assert 0 < len(expected) < len(CROSSREF_RAW["message"]["reference"])
    assert record.doi == normalize_doi(CROSSREF_RAW["message"]["DOI"])


def test_crossref_record_has_no_openalex_data():
    record = crossref.fetch_work(DOI, MAILTO, FakeTransport(CROSSREF_RAW))
    assert record.openalex_id is None
    assert record.authors == [] and record.institutions == [] and record.countries == []
    assert record.subfield is None and record.references == []


def test_crossref_request_matches_recorded_shape():
    transport = FakeTransport(CROSSREF_RAW)
    crossref.fetch_work(DOI, MAILTO, transport)
    method, url, headers, body = transport.calls[0]
    assert (method, body) == ("GET", None)
    assert url == f"https://api.crossref.org/works/{DOI}?mailto={MAILTO}"


def test_crossref_empty_mailto_sends_no_mailto():
    transport = FakeTransport(CROSSREF_RAW)
    crossref.fetch_work(DOI, "", transport)
    assert "mailto" not in transport.calls[0][1]
    assert transport.calls[0][1] == f"https://api.crossref.org/works/{DOI}"


def test_crossref_404_is_none():
    assert crossref.fetch_work(DOI, MAILTO, FakeTransport(b"Resource not found.", 404)) is None


@pytest.mark.parametrize("status", [429, 500])
def test_crossref_error_statuses_raise(status):
    with pytest.raises(ClientError) as info:
        crossref.fetch_work(DOI, MAILTO, FakeTransport(b"{}", status))
    assert info.value.status == status
    assert MAILTO not in str(info.value)


def test_osti_doi_from_fixture():
    record = osti.fetch_by_title(TITLE, FakeTransport(OSTI_RAW))
    assert record.doi == normalize_doi(OSTI_RAW[0]["doi"])
    assert record.openalex_id is None
    assert record.authors == [] and record.references == [] and record.reference_dois == []


def test_osti_missing_doi_is_none_doi():
    raw = json.loads(json.dumps(OSTI_RAW))
    del raw[0]["doi"]
    assert osti.fetch_by_title(TITLE, FakeTransport(raw)).doi is None


def test_osti_empty_result_is_none():
    assert osti.fetch_by_title(TITLE, FakeTransport([])) is None


def test_osti_404_is_none_and_errors_raise():
    assert osti.fetch_by_title(TITLE, FakeTransport(b"", 404)) is None
    with pytest.raises(ClientError):
        osti.fetch_by_title(TITLE, FakeTransport(b"", 500))


def test_osti_request_matches_recorded_shape():
    transport = FakeTransport(OSTI_RAW)
    osti.fetch_by_title(TITLE, transport)
    method, url, headers, body = transport.calls[0]
    assert (method, body) == ("GET", None)
    assert headers == {"Accept": "application/json"}
    assert url == (
        "https://www.osti.gov/api/v1/records?title="
        "Understanding%20bubble%20and%20void%20nucleation%20in%20dual%20ion%20irradiated%20T91%20steel"
        "%20using%20single%20parameter%20experiments&rows=1"
    )


def test_mailto_never_in_errors_or_logs(caplog):
    caplog.set_level(logging.DEBUG)
    for status in (200, 404, 429, 500):
        try:
            crossref.fetch_work(DOI, MAILTO, FakeTransport(CROSSREF_RAW if status == 200 else b"{}", status))
        except ClientError as err:
            assert MAILTO not in str(err) and MAILTO not in repr(err)
    assert all(MAILTO not in str(r.__dict__) for r in caplog.records)
