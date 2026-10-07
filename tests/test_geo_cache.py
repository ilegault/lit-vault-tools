"""Institution geo lookup + on-disk cache: real JSON file in tmp_path, fake transport."""

import json
from pathlib import Path

import pytest

from lit_vault_tools.clients.geo_cache import get_institution_geo, resolve_cache_dir
from lit_vault_tools.clients.http import HttpResponse
from lit_vault_tools.clients.openalex import fetch_institution_geo

FIXTURE = Path(__file__).parent / "fixtures" / "openalex_institution.json"
RAW = json.loads(FIXTURE.read_text(encoding="utf-8"))
KEY = "test-key"
ID = "I123534392"


class FakeTransport:
    def __init__(self, raw=None, status=200):
        self.body = json.dumps(RAW if raw is None else raw).encode()
        self.status = status
        self.calls = []

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url))
        return HttpResponse(self.status, self.body)


def nulled():
    raw = json.loads(json.dumps(RAW))
    raw["geo"]["latitude"] = None
    raw["geo"]["longitude"] = None
    return raw


def test_fetch_returns_fixture_coordinates():
    transport = FakeTransport()
    assert fetch_institution_geo(ID, KEY, transport) == (RAW["geo"]["latitude"], RAW["geo"]["longitude"])
    assert transport.calls == [("GET", f"https://api.openalex.org/institutions/{ID}?api_key={KEY}")]


def test_fetch_returns_none_for_null_coordinates():
    assert fetch_institution_geo(ID, KEY, FakeTransport(nulled())) is None


def test_fetch_returns_none_on_404():
    assert fetch_institution_geo(ID, KEY, FakeTransport(status=404)) is None


def test_cold_cache_fetches_once_and_writes_file(tmp_path):
    transport = FakeTransport()

    def fetch(i):
        return fetch_institution_geo(i, KEY, transport)

    first = get_institution_geo(ID, fetch, tmp_path)
    second = get_institution_geo(ID, fetch, tmp_path)
    assert first == second == (RAW["geo"]["latitude"], RAW["geo"]["longitude"])
    assert len(transport.calls) == 1
    assert (tmp_path / "institutions.json").is_file()


def test_none_is_not_cached(tmp_path):
    calls = []

    def fetch(i):
        calls.append(i)
        return None

    assert get_institution_geo(ID, fetch, tmp_path) is None
    assert get_institution_geo(ID, fetch, tmp_path) is None
    assert calls == [ID, ID]


def test_corrupt_cache_is_empty_and_rewritten_valid(tmp_path):
    (tmp_path / "institutions.json").write_text("{not json", encoding="utf-8")
    assert get_institution_geo(ID, lambda i: (1.5, 2.5), tmp_path) == (1.5, 2.5)
    assert json.loads((tmp_path / "institutions.json").read_text(encoding="utf-8"))
    assert get_institution_geo(ID, lambda i: pytest.fail("should be cached"), tmp_path) == (1.5, 2.5)


def test_corrupt_cache_rewritten_valid_even_when_lookup_finds_nothing(tmp_path):
    (tmp_path / "institutions.json").write_text("{not json", encoding="utf-8")
    assert get_institution_geo(ID, lambda i: None, tmp_path) is None
    assert json.loads((tmp_path / "institutions.json").read_text(encoding="utf-8")) == {}


def test_missing_cache_dir_is_created(tmp_path):
    target = tmp_path / "a" / "b"
    get_institution_geo(ID, lambda i: (1.0, 2.0), target)
    assert (target / "institutions.json").is_file()


def clear(monkeypatch):
    for name in ("LIT_VAULT_CACHE_DIR", "LOCALAPPDATA", "XDG_CACHE_HOME"):
        monkeypatch.delenv(name, raising=False)


def test_cache_dir_override(monkeypatch, tmp_path):
    clear(monkeypatch)
    monkeypatch.setenv("LIT_VAULT_CACHE_DIR", str(tmp_path / "o"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "l"))
    assert resolve_cache_dir() == tmp_path / "o"


def test_cache_dir_localappdata(monkeypatch, tmp_path):
    clear(monkeypatch)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "l"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "x"))
    assert resolve_cache_dir() == tmp_path / "l" / "lit-vault-tools"


def test_cache_dir_xdg(monkeypatch, tmp_path):
    clear(monkeypatch)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "x"))
    assert resolve_cache_dir() == tmp_path / "x" / "lit-vault-tools"


def test_cache_dir_home_fallback(monkeypatch, tmp_path):
    clear(monkeypatch)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    assert resolve_cache_dir() == tmp_path / ".cache" / "lit-vault-tools"


def test_nothing_written_into_vault(monkeypatch, tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "note.md").write_text("x", encoding="utf-8")
    before = sorted(p.name for p in vault.rglob("*"))
    clear(monkeypatch)
    monkeypatch.setenv("LIT_VAULT_CACHE_DIR", str(tmp_path / "cache"))
    get_institution_geo(ID, lambda i: (1.0, 2.0), resolve_cache_dir())
    assert sorted(p.name for p in vault.rglob("*")) == before
    assert (tmp_path / "cache" / "institutions.json").is_file()
