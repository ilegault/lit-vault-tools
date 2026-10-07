"""Suite-wide safety net: no test may write to a real cache directory."""

import pytest


@pytest.fixture(autouse=True)
def _isolated_cache_dir(tmp_path_factory, monkeypatch):
    monkeypatch.setenv("LIT_VAULT_CACHE_DIR", str(tmp_path_factory.mktemp("geo-cache")))


@pytest.fixture(autouse=True)
def _no_ambient_service_settings(monkeypatch):
    """CI exports bogus keys; a test that wants one sets it explicitly."""
    for name in ("S2_API_KEY", "CROSSREF_MAILTO"):
        monkeypatch.delenv(name, raising=False)
