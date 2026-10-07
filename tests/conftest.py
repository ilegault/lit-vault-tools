"""Suite-wide safety net: no test may write to a real cache directory."""

import pytest


@pytest.fixture(autouse=True)
def _isolated_cache_dir(tmp_path_factory, monkeypatch):
    monkeypatch.setenv("LIT_VAULT_CACHE_DIR", str(tmp_path_factory.mktemp("geo-cache")))
